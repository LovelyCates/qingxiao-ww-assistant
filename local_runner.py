"""Run real OK-WW tasks and write readback evidence on this computer."""
from __future__ import annotations

import argparse
import ctypes
import html
import json
import logging
import os
import re
from pathlib import Path
import sys
import traceback
import threading
import time
from datetime import datetime

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'ok-wuthering-waves-3.7.8'
GAME = None


def reconcile_stamina(initial: int, current: int, budget: int, cost: int) -> dict:
    # Reward costs are discrete. Permit one naturally regenerated point during
    # the short readback interval, without mistaking a partial/no claim for success.
    regeneration = current - (initial - budget)
    passed = 0 < budget <= initial and budget % cost == 0 and 0 <= regeneration <= 1
    return dict(consumption_verified=passed, stamina_spent=budget if passed else None,
                net_stamina_decrease=initial - current,
                natural_regeneration_inferred=regeneration if passed else None)


def daily_stamina_budget(current: int, cost: int) -> int:
    """Bound daily farming to the smallest whole-claim budget reaching 180."""
    return min(current // cost * cost, (180 + cost - 1) // cost * cost)


def main() -> int:
    global GAME
    from manual_launcher.game_window import foreground_window
    presentation_return_hwnd=foreground_window()
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['probe', 'daily', 'weekly', 'farm', 'echo', 'nightmare', 'assist', 'merge', 'enhance','multiaccount','mainstat','event'], required=True)
    parser.add_argument('--request-file', type=Path)
    parser.add_argument('--farm-target', choices=['tacet', 'simulation', 'forgery'], default='tacet')
    parser.add_argument('--reconcile-run')
    parser.add_argument('--farm-index', type=int, choices=range(1, 22), default=1)
    parser.add_argument('--simulation-material', choices=['Shell Credit', 'Resonator EXP', 'Weapon EXP'], default='Shell Credit')
    parser.add_argument('--echo-count', type=int, choices=range(1, 101), default=5)
    parser.add_argument('--echo-index', type=int, choices=range(1, 21), default=1)
    parser.add_argument('--echo-type', choices=['boss', 'weekly', 'nightmare'], default='boss')
    parser.add_argument('--nightmare-kind', choices=['all', 'purification', 'nest'], default='all')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    manual_options = {}
    if args.request_file:
        request_path = args.request_file.resolve()
        request_path.relative_to(ROOT / 'local-runs')
        manual_options = json.loads(request_path.read_text(encoding='utf-8-sig'))
        sys.path.insert(0, str(ROOT / 'manual_launcher'))
        from model import make_request, JOBS
        checked = make_request(manual_options['Action'], index=manual_options['Index'], material=manual_options['Material'],
                               count=manual_options['Count'], scope=manual_options['Scope'], kind=manual_options['Kind'],
                               duration=manual_options.get('Duration',30), background=manual_options.get('Background','background'),
                               confirmed_materials=manual_options.get('ConfirmedMaterials',False), enhance_rules=manual_options.get('EnhanceRules'),check_only=manual_options.get('CheckOnly',False),
                               stamina_limit=manual_options.get('StaminaLimit'), target_limit=manual_options.get('TargetLimit'),
                               validation_scene=manual_options.get('ValidationScene'),accounts=manual_options.get('Accounts'),
                               main_stat=manual_options.get('MainStat'),daily_farm=manual_options.get('DailyFarm'),helper_options=manual_options.get('HelperOptions'))
        if JOBS[checked['Action']][1] != args.mode:
            raise ValueError('Manual request mode mismatch')
        checked['RequestId']=manual_options['RequestId']
        manual_options = checked
    report_path = args.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    result = dict(mode=args.mode, started_at=datetime.now().astimezone().isoformat(),
                  status='STARTING', source_version='v3.7.8', game_entry=str(GAME),
                  administrator=bool(ctypes.windll.shell32.IsUserAnAdmin()),
                  game_main_observed=False, activity_points=None, weekly_garden_completed=None,
                  game_rewards_independently_verified=False, errors=[], stage='bootstrap')

    save_lock = threading.RLock()
    stop_monitor_done = threading.Event()
    parent_report = None
    child_report_path = None

    def save_unlocked(**updates):
        result.update(updates)
        result['updated_at'] = datetime.now().astimezone().isoformat()
        destination=child_report_path or report_path
        temp = destination.with_suffix('.json.tmp')
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, destination)
        from manual_launcher.reporting import write_report_html
        write_report_html(result,destination)
        if parent_report is not None:
            parent_report.update(active_step_report=str(destination),active_step_status=result['status'],
                                 active_pending_claim=result.get('pending_claim'),updated_at=result['updated_at'])
            if updates.get('status')=='CANCELLED':
                parent_report.update(status='CANCELLED',stage='stopped_by_user',ended_at=result['updated_at'])
            from manual_launcher.model import atomic_json
            atomic_json(report_path,parent_report)
            write_report_html(parent_report,report_path)

    def save(**updates):
        with save_lock:
            save_unlocked(**updates)

    save()
    if not result['administrator']:
        save(status='NEEDS_ADMIN', stage='not_started', errors=['Run this task with administrator privileges.'])
        return 5
    try:
        from manual_launcher.runtime_settings import game_executable
        GAME=game_executable(ROOT)
    except ValueError as exc:
        save(status='FAILED',stage='not_started',errors=[str(exc)])
        return 2
    save(game_entry=str(GAME) if GAME is not None else None)
    if not SOURCE.is_dir() or GAME is None or not GAME.is_file():
        save(status='FAILED', stage='not_started', errors=['请在助手偏好设置中选择游戏启动器 EXE，或配置 WW_GAME_EXE；同时检查脚本目录。'])
        return 2
    if not (SOURCE/'assets/coco_annotations.json').is_file() or not (SOURCE/'assets/echo_model/echo.onnx').is_file():
        save(status='FAILED',stage='not_started',errors=['缺少上游运行资源。请先运行 Setup.ps1 -FetchResources，从上游获取并校验资源。'])
        return 2

    os.chdir(SOURCE)
    sys.path.insert(0, str(SOURCE))
    # Keep our own mode flags out of the framework's CLI parser.
    sys.argv = [str(Path(__file__).resolve())]
    runtime = None
    window_policy = None
    try:
        from config import config as upstream_config
        from ok import OK
        from src.task.DailyTask import DailyTask, ADDITIONAL_TASKS, CHECK_WEEKLY_GARDEN
        from src.task.GardenTask import GardenTask
        from src.task.TacetTask import TacetTask
        from src.task.SimulationTask import SimulationTask
        from src.task.ForgeryTask import ForgeryTask
        from src.task.WWOneTimeTask import WWOneTimeTask
        from src.task.FarmEchoTask import FarmEchoTask
        from src.task.NightmareNestTask import NightmareNestTask
        import psutil
        from manual_launcher.game_window import prepare_existing_game
        restored_windows=prepare_existing_game()
        if restored_windows:save(existing_game_restored_from_taskbar=True)

        def watch_stop():
            owner_pid = int(os.environ.get('MC_RUN_OWNER_PID', '0'))
            try:
                owner = psutil.Process(owner_pid) if owner_pid else None
            except psutil.Error:
                owner = None
            stop_file = Path(os.environ.get('MC_STOP_FILE') or report_path.parent / 'stop-request.json')
            while not stop_monitor_done.wait(0.25):
                deadline = getattr(runtime, 'assist_deadline', None) if runtime is not None else None
                overdue = deadline is not None and time.monotonic() > deadline + 1
                if overdue or stop_file.exists() or (owner_pid and owner is None) or (owner is not None and not owner.is_running()):
                    policy_failed=False
                    if stop_file.exists():
                        try:policy_failed=json.loads(stop_file.read_text(encoding='utf-8-sig')).get('Reason')=='window_policy_error'
                        except (OSError,ValueError):pass
                    if window_policy is not None:
                        try:window_policy.finish()
                        except Exception:pass
                    if runtime is not None:
                        try:
                            runtime.exit_event.set()
                            interaction = runtime.device_manager.interaction
                            from manual_launcher.assist_guard import release_inputs
                            release_inputs(interaction)
                        except Exception:
                            pass
                    if overdue and not stop_file.exists():
                        save(status='TIMEOUT', stage='assist_deadline_exceeded',
                             assist_end_reason='helper_did_not_return',
                             errors=result['errors']+['辅助内部调用未及时返回，已强制停止并释放按键。'],
                             ended_at=datetime.now().astimezone().isoformat())
                        os._exit(2)
                    save(status='FAILED' if policy_failed else 'CANCELLED', stage='window_recovery_needed' if policy_failed else 'stopped_by_user',
                         cancellation_reason='window_policy_error' if policy_failed else 'stop_requested' if stop_file.exists() else 'launcher_closed',
                         ended_at=datetime.now().astimezone().isoformat())
                    os._exit(2 if policy_failed else 4)

        threading.Thread(target=watch_stop, name='ManualStopMonitor', daemon=True).start()

        def guarded_game_entry(_running_path=None):
            # A modal/initializing window must never cause a second game launch.
            active = [p.info['pid'] for p in psutil.process_iter(['pid', 'name'])
                      if (p.info['name'] or '').casefold() in
                      ('client-win64-shipping.exe', 'wuthering waves.exe')]
            if active:
                save(stage='existing_game_not_ready', existing_game_pids=active)
                raise RuntimeError('Game is already running but its usable window was not found; no second instance was launched.')
            return str(GAME)

        from manual_launcher.progress import read_daily_activity as read_activity

        class StartupProbe(DailyTask):
            def run(self):
                save(stage='waiting_for_game_main')
                self.ensure_main(time_out=180)
                save(game_main_observed=True, stage='reading_daily_activity',
                     startup_observations=list(result['errors']), errors=[])
                used, ready = self.open_daily()
                points = read_activity(self)
                self.screenshot('probe-daily-activity')
                # Keep the actual top-bar reading for resource-gated
                # validation. Unknown/ambiguous OCR stays raw, never zero.
                self.openF2Book('gray_book_boss')
                natural_pairs=self.ocr(.49,0,.92,.10,match=re.compile(r'^\d{1,4}/\d{1,4}$'))
                save(natural_stamina_ocr=[box.name for box in (natural_pairs or [])])
                self.screenshot('probe-natural-stamina')
                self.ensure_main(time_out=30)
                if result.get('account_scoped'):
                    uid_text=''.join(box.name for box in self.ocr(.82,.95,1,1))
                    uids=re.findall(r'(?<!\d)\d{8,12}(?!\d)',uid_text)
                    if len(uids)==1:save(game_uid=uids[0])
                save(status='PROBE_PASSED', activity_points=points,
                     daily_completed=points >= 100, detection_only=True,
                     stamina_daily_progress=used, daily_reward_ready=ready, stage='probe_finished')

        class ObservedDaily(DailyTask):
            def run(self):
                self.config['Exit After Task'] = False
                self.config[ADDITIONAL_TASKS] = []
                if manual_options.get('DailyFarm'):
                    self.config.update({'Which to Farm':{'tacet':'Tacet Suppression','forgery':'Forgery Challenge','simulation':'Simulation Challenge'}[manual_options['DailyFarm']],
                        'Which Tacet Suppression to Farm':manual_options['Index'],'Which Forgery Challenge to Farm':manual_options['Index'],
                        'Material Selection':manual_options['Material']})
                save(stage='checking_before_daily')
                self.ensure_main(time_out=180)
                save(startup_observations=list(result['errors']),errors=[])
                self.open_daily()
                initial_points = read_activity(self)
                self.screenshot('daily-before-activity')
                save(initial_activity_points=initial_points, game_main_observed=True)
                self.ensure_main(time_out=30)
                if initial_points >= 100:
                    save(status='SKIPPED_ALREADY_COMPLETE', activity_points=initial_points,
                         daily_completed=True, farming_skipped=True,
                         stage='daily_already_complete')
                    return
                save(stage='executing_real_daily')
                # Daily farming obeys the same no-refill rule as the manual farm buttons.
                import types
                def daily_natural_claim(task, once=60, must_use=0):
                    if not hasattr(task, 'farm_budget'):
                        current, _, _ = task.get_stamina()
                        # Bound the 180-stamina daily objective in whole
                        # claims: 180 for Tacet, 200 for 40-cost domains.
                        task.farm_budget = daily_stamina_budget(current, once)
                        task.farm_spent = task.farm_claims = 0
                    return NaturalStaminaOnly.use_stamina(task, once, must_use)
                for task_class in (TacetTask, ForgeryTask, SimulationTask):
                    subtask = self.get_task_by_class(task_class)
                    for field in ('farm_budget','farm_spent','farm_claims'):
                        subtask.__dict__.pop(field,None)
                    subtask.get_stamina = types.MethodType(NaturalStaminaOnly.get_stamina, subtask)
                    subtask.use_stamina = types.MethodType(daily_natural_claim, subtask)
                super().run()
                save(stage='reading_back_daily', game_main_observed=True)
                used, ready = self.open_daily()
                points = read_activity(self)
                self.screenshot('daily-result-activity')
                self.ensure_main(time_out=30)
                from manual_launcher.outcomes import daily_outcome
                outcome=daily_outcome(list(result['errors']),initial_points=initial_points,final_points=points,
                                      execution_completed=True,returned_to_main=True,
                                      pending_claim=result.get('pending_claim'))
                save(**outcome,daily_execution_completed=True,
                     activity_points=points, stamina_daily_progress=used,
                     daily_reward_ready=ready,
                     stage='daily_finished')

        class ObservedWeekly(GardenTask):
            def read_weekly_points(self):
                from manual_launcher.progress import read_weekly_progress
                points=read_weekly_progress(self)
                save(weekly_progress_points=points)
                return points

            def is_weekly_garden_completed(self):
                return self.read_weekly_points() >= 6000

            def run(self):
                self.config['Exit After Task'] = False
                save(stage='checking_weekly_progress', startup_observations=list(result['errors']), errors=[])
                WWOneTimeTask.run(self)
                self.ensure_main(time_out=90)
                self.open_garden_weekly_page()
                initial = self.read_weekly_points()
                self.screenshot('weekly-before-progress')
                save(game_main_observed=True, initial_weekly_points=initial,
                     initially_completed=initial >= 6000)
                if manual_options.get('CheckOnly'):
                    self.ensure_main(time_out=30)
                    save(status='PROBE_PASSED',weekly_garden_completed=initial>=6000,
                         detection_only=True,execution_skipped=True,stage='weekly_finished')
                    return
                if initial >= 6000:
                    self.ensure_main(time_out=30)
                    save(status='ALREADY_WEEKLY_COMPLETE', weekly_garden_completed=True,
                         execution_skipped=True, stage='weekly_finished')
                    return
                save(stage='executing_real_weekly', execution_skipped=False)
                super().run()
                self.open_garden_weekly_page()
                weekly = bool(self.is_weekly_garden_completed())
                self.screenshot('weekly-result')
                self.ensure_main(time_out=30)
                save(status='READBACK_PASSED' if weekly and not result['errors'] else 'NEEDS_REVIEW',
                     game_main_observed=True, weekly_garden_completed=weekly, stage='weekly_finished')

        class NaturalStaminaOnly:
            def get_stamina(self):
                boxes = self.wait_ocr(0.49, 0.0, 0.92, 0.10, raise_if_not_found=False,
                                      match=re.compile(r'^\d{1,4}/\d{1,4}$'))
                pairs = [re.fullmatch(r'(\d{1,4})/(\d{1,4})', b.name.strip()) for b in (boxes or [])]
                pairs = [m for m in pairs if m]
                if len(pairs) != 1 or int(pairs[0][2]) <= 0:
                    # The reward summary hides the top bar and shows "剩余 N" below.
                    if self.ocr(0.3, 0.2, 0.7, 0.4, match=re.compile('挑战成功')):
                        remaining = self.ocr(0.55, 0.85, 0.75, 0.96)
                        text = ''.join(b.name for b in (remaining or []))
                        if match := re.search(r'剩余\s*(\d{1,4})', text):
                            return int(match[1]), 0, int(match[1])
                    self.screenshot('natural-stamina-unreadable')
                    raise RuntimeError('Natural stamina is unreadable; stopped. Check screenshots for any preceding reward claim.')
                current = int(pairs[0][1])
                self.info_set('current_stamina', current)
                # Do not expose stored stamina as spendable to upstream farming loops.
                return current, 0, current

            def use_stamina(self, once=60, must_use=0):
                self.sleep(1)
                before, _, _ = self.get_stamina()
                remaining = self.farm_budget - self.farm_spent
                if before < once or remaining < once:
                    raise RuntimeError('Insufficient natural stamina/budget before claiming; no refill allowed.')
                used = once * 2 if min(before, remaining) >= once * 2 else once
                self.screenshot('before-reward-claim')
                save(stage='claiming_reward', pending_claim=dict(before=before, cost=used))
                if used == once * 2:
                    self.click_dialog_right_button()
                else:
                    self.click_dialog_left_button()
                if self.wait_feature('gem_add_stamina', horizontal_variance=0.4, vertical_variance=0.05,
                                     time_out=2, settle_time=0.5):
                    self.screenshot('unexpected-refill-cancelled')
                    self.back(after_sleep=1)
                    raise RuntimeError('Refill dialog appeared and was cancelled; no refill was confirmed.')
                self.sleep(2)
                after, _, _ = self.get_stamina()
                if before - after not in (used, used - 1):
                    self.screenshot('reward-claim-needs-review')
                    raise RuntimeError(f'Reward claim requested {used}, but stamina changed {before}->{after}; stopped without retrying the claim.')
                self.farm_spent += used
                self.farm_claims += 1
                self.screenshot('after-reward-claim')
                save(stage='farming', stamina_spent=self.farm_spent, reward_claims=self.farm_claims,
                     latest_stamina=after, latest_claim=dict(before=before, after=after, cost=used),
                     pending_claim=None)
                return after >= once and self.farm_budget - self.farm_spent >= once, used

            def run(self):
                save(stage='checking_natural_stamina', farming_target=args.farm_target,
                     farming_index=args.farm_index, simulation_material=args.simulation_material,
                     refill_allowed=False, stored_stamina_allowed=False,
                     startup_observations=list(result['errors']), errors=[])
                WWOneTimeTask.run(self)
                if args.farm_target == 'tacet':
                    self.config['Which Tacet Suppression to Farm'] = args.farm_index
                elif args.farm_target == 'forgery':
                    if args.farm_index > 20:
                        raise ValueError('Forgery index must be 1-20')
                    self.config['Which Forgery Challenge to Farm'] = args.farm_index
                if args.reconcile_run:
                    if not re.fullmatch(r'farm-\d{8}-\d{6}-\d{3}', args.reconcile_run):
                        raise ValueError('Invalid farm run identifier')
                    previous_path = ROOT / 'local-runs' / args.reconcile_run / 'report.json'
                    previous = json.loads(previous_path.read_text(encoding='utf-8-sig'))
                    if previous.get('mode') != 'farm' or previous.get('refill_allowed') is not False:
                        raise ValueError('Previous report is not a natural-stamina farm run')
                    if self.ocr(0.3, 0.2, 0.7, 0.4, match=re.compile('挑战成功')):
                        remaining, _, _ = self.get_stamina()
                        self.screenshot('reward-summary-readback')
                        save(stage='leaving_reward_summary', reward_screen_stamina=remaining)
                        leave = self.ocr(0.2, 0.78, 0.49, 0.91, match=re.compile('退出副本'))
                        if not leave:
                            raise RuntimeError('Reward summary exit button not found; did not click again.')
                        self.click(leave[0], after_sleep=2)
                    self.ensure_main(time_out=90)
                    self.openF2Book('gray_book_boss')
                    current, _, _ = self.get_stamina()
                    self.screenshot('reconciled-after-stamina')
                    self.ensure_main(time_out=30)
                    initial = previous['stamina_before']
                    accounting = reconcile_stamina(initial, current, previous['stamina_budget'], self.stamina_once)
                    passed = accounting['consumption_verified']
                    save(status='FARM_READBACK_PASSED' if passed else 'NEEDS_REVIEW',
                         stage='farm_readback_finished', game_main_observed=True,
                         reconciled_run=args.reconcile_run, source_report=str(previous_path),
                         stamina_before=initial, stamina_after=current, **accounting,
                         original_execution_status=previous['status'], original_errors=previous['errors'])
                    return
                self.ensure_main(time_out=60)
                self.openF2Book('gray_book_boss')
                before, _, _ = self.get_stamina()
                self.screenshot('farm-before-stamina')
                self.farm_budget = before // self.stamina_once * self.stamina_once
                if manual_options.get('StaminaLimit') is not None:
                    self.farm_budget=min(self.farm_budget,manual_options['StaminaLimit'])
                self.farm_spent = self.farm_claims = 0
                save(game_main_observed=True, stamina_before=before, stamina_budget=self.farm_budget,
                     stamina_spent=0, reward_claims=0, stamina_limit=manual_options.get('StaminaLimit'))
                self.ensure_main(time_out=30)
                if self.farm_budget == 0:
                    save(status='SKIPPED_INSUFFICIENT_STAMINA', stage='farm_finished', stamina_after=before)
                    return
                save(stage='healing_before_farm')
                try:
                    self.teleport_to_heal()
                except RuntimeError as heal_error:
                    save(stage='healing_at_known_location', healing_first_attempt=str(heal_error))
                    self.revive_at_tower_and_heal()
                self.screenshot('farm-after-heal')
                save(stage='entering_farm')
                if args.farm_target == 'tacet':
                    self.farm_tacet(max_recovery_retries=2)
                elif args.farm_target == 'simulation':
                    self.config['Material Selection'] = args.simulation_material
                    self.make_sure_in_world()
                    self.farm_simulation()
                else:
                    self.make_sure_in_world()
                    self.farm_forgery()
                self.ensure_main(time_out=90)
                self.openF2Book('gray_book_boss')
                after, _, _ = self.get_stamina()
                self.screenshot('farm-after-stamina')
                self.ensure_main(time_out=30)
                from manual_launcher.outcomes import farm_outcome
                outcome=farm_outcome(list(result['errors']),before=before,after=after,
                    spent=self.farm_spent,budget=self.farm_budget,reward_claims=self.farm_claims,
                    returned_to_main=True,pending_claim=result.get('pending_claim'))
                save(**outcome, stage='farm_finished',
                     stamina_after=after, stamina_spent=self.farm_spent, reward_claims=self.farm_claims)

        class ObservedTacet(NaturalStaminaOnly, TacetTask):
            pass

        class ObservedSimulation(NaturalStaminaOnly, SimulationTask):
            pass

        class ObservedForgery(NaturalStaminaOnly, ForgeryTask):
            pass

        class ObservedEcho(FarmEchoTask):
            def combat_once(self,*args,**kwargs):
                save(stage='echo_combat',combat_observations=self.observed_combats)
                self.screenshot('echo-combat-entry')
                entered=super().combat_once(*args,**kwargs)
                if entered:self.observed_combats+=1
                self.screenshot('echo-combat-return')
                save(stage='echo_pickup',combat_observations=self.observed_combats)
                return entered

            def incr_drop(self,dropped):
                super().incr_drop(dropped)
                if dropped:
                    count=self.info.get('Echo Count',0)
                    self.screenshot('echo-pickup-'+str(count))
                    save(echo_count=count)

            def use_stamina(self, *unused, **unused_keywords):
                raise RuntimeError('Boss echo mode never spends stamina.')

            def run(self, retries=0):
                self.observed_combats=0
                maximum = {'boss': 20, 'weekly': 9, 'nightmare': 10}[args.echo_type]
                if args.echo_index > maximum:
                    raise ValueError('Boss index exceeds selected category')
                self.config['Exit After Task'] = False
                self.config['Repeat Farm Count'] = args.echo_count
                self.config['Teleport to Boss'] = {'boss': 'Boss Challenge', 'weekly': 'Weekly Challenge', 'nightmare': 'Special Nightmare'}[args.echo_type]
                self.config[{'boss': 'Which Boss Challenge to Teleport', 'weekly': 'Which Weekly Boss to Teleport', 'nightmare': 'Which Special Nightmare to Teleport'}[args.echo_type]] = args.echo_index
                save(stage='executing_echo', requested_rounds=args.echo_count, boss_type=args.echo_type,
                     boss_index=args.echo_index, startup_observations=list(result['errors']), errors=[])
                self.ensure_main(time_out=90)
                super().run(retries=retries)
                self.screenshot('echo-result')
                self.ensure_main(time_out=60)
                from manual_launcher.outcomes import echo_outcome
                count=self.info.get('Echo Count',0)
                outcome=echo_outcome(list(result['errors']),pickups=count,
                    observed_combats=self.observed_combats,requested_rounds=args.echo_count,returned_to_main=True)
                save(**outcome,game_main_observed=True,echo_count=count,
                     combat_observations=self.observed_combats,stage='echo_finished')

        class ObservedNightmare(NightmareNestTask):
            def combat_once(self,*args,**kwargs):
                entered=super().combat_once(*args,**kwargs)
                if entered:self.observed_combats+=1
                save(combat_observations=self.observed_combats)
                return entered

            def get_nest_to_go(self):
                limit=manual_options.get('TargetLimit')
                if limit is not None and self.observed_targets>=limit:return None
                return super().get_nest_to_go()

            def combat_nest(self,nest):
                self.observed_targets+=1
                self._capture_success=False
                save(stage='nightmare_combat',nightmare_targets_attempted=self.observed_targets)
                self.screenshot('nightmare-target-entry')
                super().combat_nest(nest)
                if self._capture_success:self.observed_captures+=1
                self.screenshot('nightmare-target-return')
                save(nightmare_targets_attempted=self.observed_targets,nightmare_captured_targets=self.observed_captures)

            def use_stamina(self, *unused, **unused_keywords):
                raise RuntimeError('Nightmare mode never spends stamina.')

            def run(self):
                self.observed_targets=self.observed_captures=self.observed_combats=0
                if manual_options.get('TargetLimit'):
                    from manual_launcher.liberation_probe import LiberationProbe
                    self.liberation_probe=LiberationProbe(self,report_path.parent)
                self.config['Which to Farm'] = {'all': ['Nightmare Purification', 'Tacet Discord Nest'],
                    'purification': ['Nightmare Purification'], 'nest': ['Tacet Discord Nest']}[args.nightmare_kind]
                save(stage='executing_nightmare', nightmare_kind=args.nightmare_kind,
                     target_limit=manual_options.get('TargetLimit'),
                     nightmare_targets_attempted=0,nightmare_captured_targets=0,
                     startup_observations=list(result['errors']), errors=[])
                super().run()
                self.screenshot('nightmare-result')
                self.ensure_main(time_out=60)
                from manual_launcher.outcomes import echo_outcome
                outcome=echo_outcome(list(result['errors']),pickups=self.observed_captures,
                    observed_combats=self.observed_combats,requested_rounds=max(1,self.observed_targets),
                    returned_to_main=True)
                if not self.observed_targets and not outcome['errors']:
                    outcome['status']='NO_ELIGIBLE_ECHOES'
                save(**outcome,game_main_observed=True,combat_observations=self.observed_combats,
                     stage='nightmare_finished')

        if args.mode=='multiaccount':
            from src.task.MultiAccountConfigTask import MultiAccountConfigTask
            from src.task.account.RuntimeTaskConfig import isolated_task_configs,effective_config
            from manual_launcher.accounts import execute_accounts

            class ObservedMultiAccount(MultiAccountConfigTask):
                active_child=None

                def sleep_check(self):
                    if self.active_child is not None:self.active_child.sleep_check()

                def ensure_main(self,esc=True,time_out=180):
                    # Account auth challenges need human input. Never turn a
                    # missing saved session into blind password/OTP clicks.
                    def ready():
                        if self.ocr(match=re.compile('请输入.*(?:密码|验证码)|请.*(?:扫码|安全验证|人机验证)|拖动.*滑块|完成.*验证')):
                            self.screenshot('account-login-needs-user')
                            raise RuntimeError('该账号需要本人完成登录验证；整轮已停止。')
                        return self.is_main(esc=esc)
                    self.wait_until(ready,time_out=time_out,raise_if_not_found=True)
                    self.sleep(.5)

                def run_child(self,profile,step,index):
                    nonlocal result,parent_report,child_report_path,manual_options
                    action=step['action'];opts=dict(step['options']);daily_farm=opts.pop('daily_farm','tacet')
                    from manual_launcher.model import make_request,JOBS
                    request=make_request(daily_farm if action=='daily' else action,background='foreground',**opts)
                    mode='daily' if action=='daily' else JOBS[action][1]
                    classes={'probe':StartupProbe,'daily':ObservedDaily,'weekly':ObservedWeekly,
                        'tacet':ObservedTacet,'forgery':ObservedForgery,'simulation':ObservedSimulation,
                        'echo':ObservedEcho,'nightmare':ObservedNightmare}
                    child=classes[action](executor=self.executor,app=self._app)
                    child.after_init(executor=self.executor,scene=self.executor.scene);child.post_init()
                    child.config=effective_config(child,{})
                    if action=='daily':
                        child.config.update({'Which to Farm':{'tacet':'Tacet Suppression','forgery':'Forgery Challenge','simulation':'Simulation Challenge'}[daily_farm],
                            'Which Tacet Suppression to Farm':request['Index'],'Which Forgery Challenge to Farm':request['Index'],
                            'Material Selection':request['Material']})
                    old_args=vars(args).copy();old_options=manual_options;outer=result
                    path=report_path.parent/'accounts'/profile['id']/str(index)/'report.json';path.parent.mkdir(parents=True,exist_ok=True)
                    (path.parent/'screenshots').mkdir(exist_ok=True)
                    old_screenshots=runtime.screenshot.screenshot_folder
                    with save_lock:
                        parent_report=outer;child_report_path=path
                        result=dict(mode=mode,status='STARTING',stage='bootstrap',errors=[],
                            started_at=datetime.now().astimezone().isoformat(),administrator=outer['administrator'],
                            source_version=outer['source_version'],account_scoped=True,account_id=profile['id'],account_label=profile['label'])
                        manual_options=request
                        runtime.screenshot.screenshot_folder=str(path.parent/'screenshots')
                        args.farm_target=action;args.farm_index=request['Index'];args.simulation_material=request['Material']
                        args.echo_count=request['Count'];args.echo_index=request['Index'];args.echo_type=request['Scope'];args.nightmare_kind=request['Kind']
                        args.reconcile_run=None
                        save(stage='starting_task')
                    try:
                        self.active_child=child
                        with isolated_task_configs(self.executor.get_all_tasks()):
                            for subtask in self.executor.get_all_tasks():
                                if hasattr(subtask,'reset_combat_state'):subtask.reset_combat_state('account step start')
                                if hasattr(subtask,'map_zoomed'):subtask.map_zoomed=False
                            child.run()
                        if result['status']=='STARTING':save(status='FAILED',errors=result['errors']+['步骤没有完成回执。'])
                    except BaseException as exc:
                        save(status='CANCELLED' if type(exc).__name__=='TaskDisabledException' else 'FAILED',
                             errors=result['errors']+[f'{type(exc).__name__}: {exc}'])
                    finally:
                        self.active_child=None
                        with save_lock:
                            save(ended_at=datetime.now().astimezone().isoformat())
                            receipt={k:result[k] for k in ('status','errors','activity_points','weekly_progress_points','stamina_spent','pending_claim','echo_count','game_uid') if k in result}
                            receipt.update(action=action,report=str(path))
                            result=outer;parent_report=None;child_report_path=None;manual_options=old_options
                            runtime.screenshot.screenshot_folder=old_screenshots
                            vars(args).clear();vars(args).update(old_args)
                    return receipt

                def run(self):
                    save(stage='account_preflight',refill_allowed=False,stored_stamina_allowed=False)
                    if manual_options.get('ValidationScene')=='account_inventory':
                        from manual_launcher.account_inventory import read_saved_accounts
                        labels=read_saved_accounts(self)
                        save(status='PROBE_PASSED',stage='account_inventory_finished',saved_account_labels=labels,
                             detection_only=True,account_inventory_only=True)
                        return
                    def publish(rows,label):
                        current=next((row['id'] for row in rows if row['status'] in ('logging_in','running')),None)
                        save(account_results=rows,current_account=label,current_account_id=current,
                             stage='account_tasks',active_step_report=None,active_pending_claim=None)
                    def prepare():
                        WWOneTimeTask.run(self);self.logged_in=False
                        if self._login_combo() or self.do_find_account_drop_down():return
                        self.ensure_main(time_out=180)
                        save(startup_observations=list(result['errors']),errors=[])
                        self._switch_to_login()
                    def login(key):
                        # Every new account is selected and verified, including
                        # the first one. Never run on the initial arbitrary user.
                        if not (self._login_combo() or self.do_find_account_drop_down()):self._switch_to_login()
                        self._login_target_account(key)
                        self.screenshot('account-login-confirmed')
                    rows=execute_accounts(manual_options['Accounts'],prepare,login,self.run_child,publish,
                                          check_stop=self.executor.check_enabled)
                    save(status='EXECUTION_FINISHED' if not result['errors'] else 'NEEDS_REVIEW',stage='accounts_finished',account_results=rows,
                         accounts_completed=len(rows),current_account_id=None,active_step_report=None)

        config = dict(upstream_config)
        config.pop('gui', None)
        config['use_gui'] = False
        config['debug'] = False
        config['locale'] = 'zh_CN'
        config['config_folder'] = str(ROOT / 'local-game-config')
        config['screenshots_folder'] = str(report_path.parent / 'screenshots')
        config['log_file'] = str(report_path.parent / 'ok-ww.log')
        config['error_log_file'] = str(report_path.parent / 'ok-ww-error.log')
        config['windows'] = dict(config['windows'])
        config['windows']['calculate_pc_exe_path'] = guarded_game_entry
        # Default HD resources match the official launcher selection observed here.
        config['windows']['launch_arguments'] = '-krqlv=hd -SkipSplash'
        if args.mode == 'probe':
            config['trigger_tasks'] = [['src.task.AutoLoginTask', 'AutoLoginTask']]
        elif args.mode in ('farm', 'weekly', 'echo', 'nightmare', 'assist', 'merge','enhance','multiaccount','mainstat','event'):
            config['trigger_tasks'] = [['src.task.MouseResetTask', 'MouseResetTask']]
        save(stage='initializing_ok_ww')
        runtime = OK(config)
        if manual_options:
            from manual_launcher.game_window import GameWindowPolicy
            window_policy=GameWindowPolicy(runtime,manual_options.get('Background','background'),save,
                                           report_path.parent/'window-command.json',manual_options['RequestId'],
                                           return_hwnd=presentation_return_hwnd)
            window_policy.start()

        class RunErrors(logging.Handler):
            def emit(self, record):
                if record.levelno >= logging.ERROR:
                    message = record.getMessage()
                    if message not in result['errors'] and len(result['errors']) < 30:
                        result['errors'].append(message[:1600])

        logging.getLogger().addHandler(RunErrors())
        tasks = {'probe': StartupProbe, 'daily': ObservedDaily, 'weekly': ObservedWeekly,
                'echo': ObservedEcho, 'nightmare': ObservedNightmare,
                'farm': {'tacet': ObservedTacet, 'simulation': ObservedSimulation,
                         'forgery': ObservedForgery}[args.farm_target]}
        if args.mode=='multiaccount':tasks['multiaccount']=ObservedMultiAccount
        if args.mode in ('assist','merge','enhance','mainstat','event'):
            from manual_launcher.game_extensions import task_classes
            if not manual_options:
                raise ValueError('Extended tasks must be started from a validated panel request.')
            tasks.update(task_classes(runtime,save,result,manual_options,report_path.parent))
        task = tasks[args.mode]
        save(stage='starting_task')
        runtime.run_task(task, exit_after=False)
        if result['status'] == 'STARTING':
            save(status='FAILED', stage='task_ended_without_readback',
                 errors=result['errors'] + ['The task ended without writing its completion evidence.'])
    except BaseException as exc:
        save(status='FAILED', stage='exception',
             errors=result['errors'] + [f'{type(exc).__name__}: {exc}'], traceback=traceback.format_exc())
    finally:
        stop_monitor_done.set()
        if window_policy is not None:
            try:window_policy.finish()
            except Exception as exc:save(window_cleanup_error=str(exc))
        save(ended_at=datetime.now().astimezone().isoformat())
        if runtime is not None:
            try:
                runtime.quit()
            except BaseException:
                pass
    return 0 if result['status'] in ('PROBE_PASSED', 'READBACK_PASSED', 'SKIPPED_ALREADY_COMPLETE',
                                   'FARM_PASSED', 'FARM_READBACK_PASSED', 'SKIPPED_INSUFFICIENT_STAMINA',
                                   'ALREADY_WEEKLY_COMPLETE', 'EXECUTION_FINISHED','ASSIST_FINISHED','NO_ELIGIBLE_ECHOES') else 2


if __name__ == '__main__':
    raise SystemExit(main())
