"""Bounded adapters around installed OK-WW tasks. Imported only by game workers."""
import time
from contextlib import nullcontext
try:
    from .assist_guard import AssistDeadlineReached, executor_deadline, release_inputs
    from .model import normalize_enhance_rules,normalize_helper_options
except ImportError:
    from assist_guard import AssistDeadlineReached, executor_deadline, release_inputs
    from model import normalize_enhance_rules,normalize_helper_options

def task_classes(runtime, save, result, options, run_directory):
    from src.task.BaseWWTask import BaseWWTask
    from src.task.AutoPickTask import AutoPickTask
    from src.task.SkipDialogTask import AutoDialogTask
    from src.task.AutoCombatTask import AutoCombatTask
    from src.task.MergeEchoTask import MergeEchoTask
    from src.task.EnhanceEchoTask import EnhanceEchoTask
    from src.task.ChangeEchoTask import ChangeEchoTask
    from src.task.FastTravelTask import FastTravelTask
    from src.task.TacetEliminationTask import TacetEliminationTask

    class AssistedPlay(BaseWWTask):
        active_helper = None
        def sleep_check(self):
            # Executor.current_task is this adapter. Forward the active
            # helper's periodic combat checks instead of silently disabling
            # the checks normally used when it runs as a trigger task.
            if self.active_helper is not None:
                self.active_helper.sleep_check()
        def run(self):
            scene=options.get('ValidationScene')
            if scene:
                try:
                    from .validation_scenes import assist_scene
                except ImportError:
                    from validation_scenes import assist_scene
                preparation=assist_scene(self,scene,save)
            else:preparation=nullcontext()
            try:
                with preparation:self.run_helpers()
            except Exception as exc:
                if scene:save(status='NEEDS_REVIEW',stage='validation_scene_failed',stop_reason=str(exc))
                raise

        def run_helpers(self):
            action = options['Action']
            # Preserve the user's current scene, especially an ongoing dialog.
            # Helpers already gate themselves on their relevant scene.
            settings=normalize_helper_options(options.get('HelperOptions'))
            selected = {'pickup':[AutoPickTask], 'dialog':[AutoDialogTask],
                        'combat':[AutoCombatTask, AutoPickTask],'fasttravel':[FastTravelTask],
                        'quest':[cls for key,cls in (('quest_dialog',AutoDialogTask),('quest_combat',AutoCombatTask),
                            ('quest_pickup',AutoPickTask),('quest_fasttravel',FastTravelTask)) if settings[key]]}[action]
            helpers = []
            for cls in selected:
                helper = cls(executor=self.executor, app=self._app)
                helper.after_init(executor=self.executor, scene=self.executor.scene)
                helper.post_init()
                if cls is AutoCombatTask:helper.config.update({'Auto Target':settings['auto_target'],
                    'Use Liberation':settings['use_liberation'],'Switch to Healer before and after Combat':settings['switch_healer']})
                if cls is AutoPickTask:helper.config.update({'Pick Up White List':settings['pickup_whitelist'],'Pick Up Black List':settings['pickup_blacklist']})
                if cls is AutoCombatTask and options.get('ValidationScene') in ('combat_boss','combat_tacet'):
                    try:
                        from .liberation_probe import LiberationProbe
                    except ImportError:
                        from liberation_probe import LiberationProbe
                    helper.liberation_probe=LiberationProbe(helper,run_directory)
                helpers.append(helper)
            minutes = options.get('Duration',30)
            started = time.monotonic()
            deadline = started + minutes*60
            if runtime is not None:
                runtime.assist_deadline = deadline
            last_save = 0
            cycles = 0
            events = {'pickup_interactions':0, 'combat_sessions':0, 'dialog_actions':0,'travel_actions':0}
            validation_confirmed=False
            last_validation_check=0
            save(stage='assisting_play', assist_action=action, duration_minutes=minutes,
                 startup_observations=list(result['errors']), errors=[], **events)
            try:
                with executor_deadline(self.executor, deadline, clock=time.monotonic):
                    while time.monotonic() < deadline:
                        for helper in helpers:
                            self.executor.check_enabled()
                            self.active_helper=helper
                            self.sleep_check_interval=getattr(helper,'sleep_check_interval',-1)
                            try:
                                acted = helper.run()
                            finally:
                                self.active_helper=None
                                self.sleep_check_interval=-1
                            if acted:
                                key = 'pickup_interactions' if isinstance(helper, AutoPickTask) else 'combat_sessions' if isinstance(helper, AutoCombatTask) else 'travel_actions' if isinstance(helper,FastTravelTask) else 'dialog_actions'
                                events[key] += 1
                                if options.get('ValidationScene'):
                                    self.sleep(.6)
                                    try:
                                        from .validation_scenes import verify_assist_event
                                    except ImportError:
                                        from validation_scenes import verify_assist_event
                                    confirmed=verify_assist_event(self,options['ValidationScene'],save)
                                    validation_confirmed=validation_confirmed or confirmed
                                    last_validation_check=time.monotonic()
                                    self.screenshot('assist-observed-'+key+'-'+str(events[key]))
                                    save(**events)
                        cycles += 1
                        if (options.get('ValidationScene')=='combat_tacet' and events['combat_sessions']>0
                                and not validation_confirmed and time.monotonic()-last_validation_check>=1):
                            validation_confirmed=verify_assist_event(self,'combat_tacet',save)
                            last_validation_check=time.monotonic()
                        if options.get('ValidationScene') and validation_confirmed:
                            break
                        elapsed = time.monotonic()-started
                        if elapsed-last_save >= 3:
                            save(assist_elapsed_seconds=round(elapsed), assist_cycles=cycles, **events)
                            last_save = elapsed
                        self.sleep(0.35 if action=='combat' else 0.55)
            except AssistDeadlineReached:
                pass
            finally:
                if runtime is not None:
                    runtime.assist_deadline = None
                    release_inputs(runtime.device_manager.interaction)
            if options.get('ValidationScene') and not validation_confirmed:
                raise RuntimeError('辅助验证时限内没有确认目标事件完成，请查看实际进度截图')
            try:
                from .outcomes import assist_outcome
            except ImportError:
                from outcomes import assist_outcome
            outcome=assist_outcome(list(result['errors']),completed_combat_sessions=events['combat_sessions'],normal_ending=True)
            save(**outcome,
                 stage='assist_finished', assist_elapsed_seconds=round(time.monotonic()-started),
                 assist_cycles=cycles,
                 assist_end_reason=('validation_event_observed' if options.get('ValidationScene') and any(events.values())
                                    else 'duration_reached'), **events)

    class BoundedMerge(MergeEchoTask):
        def run(self):
            if options.get('CheckOnly'):
                save(stage='checking_merge_page', check_only=True, merge_batches=0)
                labels = self.inspect_merge_filter()
                selected = self.select_discarded_batch()
                save(status='PROBE_PASSED', stage='merge_page_checked', merge_filter_labels=labels,
                     discard_filter_verified=True, merge_selected_materials=selected,
                     material_consumption_independently_verified=True)
                return
            if not options.get('ConfirmedMaterials'):
                raise RuntimeError('请在助手中核对并确认弃置声骸合成。')
            self.completed_batches = 0
            save(stage='merging_discarded_echoes', merge_batches=0, merge_limit=options['Count'])
            try:
                self.merge_echoes()
            except Exception as exc:
                save(status='NEEDS_REVIEW', stage='merge_interrupted', merge_batches=self.completed_batches,
                     stop_reason=str(exc), material_consumption_independently_verified=False)
                raise
            self.screenshot('merge-result')
            self.ensure_main(time_out=30)
            save(status=('EXECUTION_FINISHED' if self.completed_batches else 'NO_ELIGIBLE_ECHOES') if not result['errors'] else 'NEEDS_REVIEW',
                 stage='merge_finished', merge_batches=self.completed_batches,
                 game_main_observed=True, material_consumption_independently_verified=False)
        def merge_full_batch(self):
            if self.completed_batches >= options['Count']:
                return False
            merged = super().merge_full_batch()
            if merged:
                self.completed_batches += 1
                save(merge_batches=self.completed_batches)
            return merged

    class BoundedEnhance(EnhanceEchoTask):
        def run(self):
            resume=options.get('ValidationScene')=='echo_current_resume'
            if resume:
                try:
                    from .validation_scenes import prepare_current_echo
                except ImportError:
                    from validation_scenes import prepare_current_echo
                prepare_current_echo(self,save)
            if options.get('ValidationScene')=='echo_inventory':
                try:
                    from .validation_scenes import prepare_echo_inventory
                except ImportError:
                    from validation_scenes import prepare_echo_inventory
                prepare_echo_inventory(self,save)
            if options.get('CheckOnly'):
                save(stage='checking_echo_page')
                self.screenshot('enhance-preflight')
                if not self.find_echo_enhance():
                    raise RuntimeError('请先在游戏中打开背包声骸页，再检查。')
                level = self.read_selected_level()
                save(status='PROBE_PASSED', stage='echo_page_checked', selected_echo_level=level,
                     check_only=True, material_consumption_independently_verified=True,
                     enhance_selected=0, enhance_success=0, enhance_rejected=0)
                return
            if not options.get('ConfirmedMaterials'):
                raise RuntimeError('请核对声骸筛选与强化规则后明确开始。')
            self.selected_count = 0
            rules = normalize_enhance_rules(options['EnhanceRules'])
            self.config.update({'必须有双爆':rules['require_double_crit'], '有效词条':rules['valid_stats'],
                                '有效词条>=':rules['minimum_valid'],'双爆总计>=':rules['crit_score'],
                                '首条双爆>=':rules['first_crit'],
                                '双爆出现之前必须全有效词条':rules['require_valid_before_crit'],
                                '第一条必须为有效词条':rules['require_first_valid'], 'Pause after Success':False})
            save(stage='enhancing_echoes', enhance_limit=options['Count'], enhance_selected=0,
                 enhance_rules=rules, startup_observations=list(result['errors']), errors=[])
            try:
                if resume:
                    self.selected_count=1
                    self.info_set('成功声骸数量',0)
                    self.info_set('失败声骸数量',0)
                    if not self.read_stat_decision(2):
                        self.trash_and_esc()
                    else:
                        self.enhance_selected_echo(3)
                else:
                    super().run()
            except Exception as exc:
                save(status='NEEDS_REVIEW', stage='enhance_interrupted', stop_reason=str(exc),
                     enhance_selected=self.selected_count, enhance_success=self.info_get('成功声骸数量'),
                     enhance_rejected=self.info_get('失败声骸数量'),
                     material_consumption_independently_verified=False)
                raise
            self.screenshot('enhance-result')
            save(status=('EXECUTION_FINISHED' if self.selected_count else 'NO_ELIGIBLE_ECHOES') if not result['errors'] else 'NEEDS_REVIEW',
                 stage='enhance_finished', enhance_selected=self.selected_count,
                 enhance_success=self.info_get('成功声骸数量'), enhance_rejected=self.info_get('失败声骸数量'),
                 material_consumption_independently_verified=False)
        def prepare_evidence(self):
            # Each worker already owns a unique run directory. Never clear
            # shared screenshots or patch global os.startfile to suppress UI.
            pass
        def open_evidence(self):
            pass
        def select_0_level_echo(self):
            if self.selected_count >= options['Count']:
                return False
            selected = super().select_0_level_echo()
            if selected:
                self.selected_count += 1
                save(enhance_selected=self.selected_count)
            return selected

    class BoundedReconstruct(ChangeEchoTask):
        read_selected_level=EnhanceEchoTask.read_selected_level

        def open_evidence(self):pass

        def is_0_level(self):
            if self.info_get('成功声骸数量')>=options['Count']:return False
            return self.read_selected_level()==0

        def before_reconstruct(self,target,current):
            self.screenshot('before-main-stat-reconstruct')
            save(pending_reconstruct=dict(target=target,previous=current),stage='reconstruct_submitting')

        def after_reconstruct(self):
            self.screenshot('after-main-stat-reconstruct')
            save(reconstruct_completed=self.info_get('成功声骸数量'),pending_reconstruct=None)

        def run(self):
            if options.get('CheckOnly'):
                if not self.find_echo_enhance():raise RuntimeError('请先打开游戏背包声骸页。')
                level=self.read_selected_level();self.screenshot('reconstruct-preflight')
                save(status='PROBE_PASSED',stage='reconstruct_checked',check_only=True,selected_echo_level=level,
                     reconstruct_completed=0,reconstruct_target=options['MainStat'])
                return
            if not options.get('ConfirmedMaterials'):raise RuntimeError('请核对候选、目标主属性与材料消耗后再开始重构。')
            self.config['目标属性']=options['MainStat']
            save(stage='reconstructing',reconstruct_completed=0,reconstruct_limit=options['Count'],
                 reconstruct_target=options['MainStat'],material_consumption_independently_verified=False)
            try:super().run()
            except Exception as exc:
                save(status='NEEDS_REVIEW',stage='reconstruct_interrupted',stop_reason=str(exc))
                raise
            count=self.info_get('成功声骸数量')
            save(status=('EXECUTION_FINISHED' if count else 'NO_ELIGIBLE_ECHOES') if not result['errors'] else 'NEEDS_REVIEW',
                 stage='reconstruct_finished',reconstruct_completed=count,
                 main_attribute_independently_verified=False)

    class BoundedElimination(TacetEliminationTask):
        def info_set(self,key,value):
            super().info_set(key,value)
            if key in ('Completed stages','Claimed rewards'):
                save(**{'event_stages' if key=='Completed stages' else 'event_reward_claims':value})

        def run(self):
            if options.get('CheckOnly'):
                self.prepare_event();self.screenshot('event-preflight')
                save(status='PROBE_PASSED',stage='event_checked',check_only=True,event_stages=0,event_completed=False)
                return
            deadline=time.monotonic()+options['Duration']*60
            if runtime is not None:runtime.assist_deadline=deadline
            ended='upstream_returned';save(stage='executing_event',event_stages=0,event_reward_claims=0,event_completed=False)
            try:
                with executor_deadline(self.executor,deadline,clock=time.monotonic):super().run()
            except AssistDeadlineReached:ended='time_limit'
            finally:
                if runtime is not None:
                    runtime.assist_deadline=None
                    release_inputs(runtime.device_manager.interaction)
            self.screenshot('event-result')
            save(status='EXECUTION_FINISHED' if not result['errors'] else 'NEEDS_REVIEW',stage='event_finished',
                 event_stages=getattr(self,'completed_stages',0),event_reward_claims=getattr(self,'claimed_rewards',0),
                 event_end_reason=ended,event_completed=ended=='upstream_returned')

    return {'assist':AssistedPlay, 'merge':BoundedMerge, 'enhance':BoundedEnhance,
            'mainstat':BoundedReconstruct,'event':BoundedElimination}
