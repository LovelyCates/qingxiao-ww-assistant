"""Explicit local test preparation, using installed OK-WW navigation only.

No scene is prepared in normal user runs. These finite, allowlisted scenarios
never claim a stamina reward and never replace the auxiliary implementation.
"""
import time
import re
from contextlib import contextmanager


@contextmanager
def assist_scene(adapter,scene,save):
    if scene=='dialog_phone':
        with phone_dialog_scene(adapter,save):yield
        return
    if scene=='combat_tacet':
        with tacet_combat_scene(adapter,save):yield
        return
    if scene not in ('combat_boss','pickup_echo'):raise ValueError('Unknown fixed validation scene')
    from src.task.FarmEchoTask import FarmEchoTask
    from src.task.WWOneTimeTask import WWOneTimeTask
    boss=adapter.get_task_by_class(FarmEchoTask)
    keys={'Teleport to Boss':'Boss Challenge','Which Boss Challenge to Teleport':1,
          'Boss':'Other','Repeat Farm Count':1,'Exit After Task':False}
    previous={key:boss.config.get(key) for key in keys}
    save(stage='preparing_validation_scene',validation_scene=scene)
    try:
        boss.config.update(keys)
        WWOneTimeTask.run(boss)
        boss.ensure_main(time_out=90)
        boss._farm_start_time=time.time()
        boss.manage_boss_parameters()
        boss.init_parameters()
        boss.teleport_to_configured_boss_and_prepare()
        if not boss.wait_until(lambda:boss.in_combat(target=True),time_out=30,
                               raise_if_not_found=False,post_action=lambda:boss.click()):
            raise RuntimeError('验证场景未进入真实战斗，未将空循环计为通过')
        boss.screenshot('validation-combat-ready')
        if scene=='pickup_echo':
            boss.combat_once(wait_combat_time=5,raise_if_not_found=True)
            # Reuse navigation but stop at the Absorb prompt. The production
            # AutoPickTask, rather than the setup, must perform the actual F.
            original_f,original_echo=boss.pick_f,boss.pick_echo
            def absorb_visible(*args,**kwargs):
                return bool(boss.find_f_with_text(target_text=boss.absorb_echo_text()))
            try:
                boss.pick_f=boss.pick_echo=absorb_visible
                found=bool(boss.yolo_find_echo(turn=True,time_out=30)[0])
            finally:
                boss.pick_f,boss.pick_echo=original_f,original_echo
            if not found or not absorb_visible():
                raise RuntimeError('战后没有找到未吸收声骸，未验证实际拾取')
            boss.screenshot('validation-absorb-ready')
        save(validation_scene_ready=True)
        yield
    finally:
        boss.config.update(previous)
        # The context runs outside the bounded helper's deadline wrapper.
        # Return to a known game state after the auxiliary test is finished.
        boss.ensure_main(time_out=60)


def prepare_echo_inventory(task,save):
    """Select a zero-level, discarded-only candidate without cultivating it."""
    from src.task.MergeEchoTask import MergeEchoTask
    save(stage='preparing_echo_candidate')
    task.ensure_main(time_out=60)
    task.send_key(task.key_config.get('Bag Key','b'),after_sleep=1)
    task.click_relative(.04,.294,after_sleep=1)
    task.wait_until(task.find_echo_enhance,time_out=10,raise_if_not_found=True)
    task.click_relative(.11,.917,after_sleep=.5)
    task.wait_ocr(.65,0,.98,.12,match='筛选',raise_if_not_found=True)
    task.wait_click_ocr(.65,.79,.98,.88,match='重置',raise_if_not_found=True,after_sleep=.5)
    task.wait_click_ocr(.67,.17,.77,.24,match=re.compile(r'^已[弃棄]置$'),raise_if_not_found=True,after_sleep=.5)
    if MergeEchoTask.read_discard_filter_state(task)!=(True,False,False):
        raise RuntimeError('未确认只选已弃置候选，未开始强化')
    task.screenshot('enhance-candidate-filter-verified')
    task.click_relative(.943,.06,after_sleep=.5)
    task.click_relative(.13,.21,after_sleep=.5)
    if task.read_selected_level()!=0:
        task.click_relative(.35,.917,after_sleep=.5)
        task.click_relative(.13,.21,after_sleep=.5)
    if task.read_selected_level()!=0:raise RuntimeError('已弃置筛选下没有可选0级候选，未开始强化')
    task.screenshot('enhance-candidate-zero')
    save(validation_candidate_filter='discarded_only',validation_candidate_level=0)


def verify_assist_event(task,scene,save):
    if scene=='pickup_echo':
        task.next_frame()
        if task.find_f_with_text(target_text=task.absorb_echo_text()):
            raise RuntimeError('辅助按键后吸收提示仍存在，未确认实际拾取')
        save(validation_pickup_prompt_cleared=True)
    elif scene=='combat_tacet':
        lines=[b.name for b in task.ocr(.005,.16,.32,.42)]
        task.screenshot('validation-tacet-segment')
        save(validation_tacet_progress_text=lines)
        if not any(re.search(r'领取奖励|挑战成功|挑战已完成|清剿完成',line) for line in lines):
            if task.find_treasure_icon():
                # Current Tacet clears its quest text when the reward chest
                # appears. Approach only, then verify its F label; never
                # open the stamina claim dialog in this combat-only test.
                task.walk_to_treasure(send_f=False)
                if task.find_f_with_claim_text():
                    save(validation_tacet_reward_prompt_confirmed=True,
                         validation_combat_victory_confirmed=True)
                    task.screenshot('validation-tacet-reward-without-claim')
                    return True
            # A target gap between waves ends one AutoCombatTask session.
            # Keep the helper running until the actual objective is complete.
            return False
        save(validation_combat_victory_confirmed=True)
    elif scene=='combat_boss':
        def victory_visible():
            return task.ocr(.005,.18,.30,.40,match=re.compile('领取奖励|挑战成功'))
        if not task.wait_until(victory_visible,time_out=8,raise_if_not_found=False):
            raise RuntimeError('辅助战斗返回后未看到挑战完成或领奖提示')
        save(validation_combat_victory_confirmed=True)
    elif scene=='dialog_phone':
        before=task._validation_phone_text
        def changed():
            lines=phone_dialog_text(task)
            return bool(lines and lines!=before) or task.in_team_and_world()
        if not task.wait_until(changed,time_out=8,raise_if_not_found=False):
            raise RuntimeError('飞讯辅助点击后内容没有变化，未确认实际对话动作')
        save(validation_dialog_content_changed=True,validation_dialog_after=phone_dialog_text(task))
    task.screenshot('validation-assist-event-confirmed')
    return True


def phone_dialog_text(task):
    return [b.name for b in task.ocr(.20,.25,.80,.80)]


@contextmanager
def tacet_combat_scene(task,save):
    """Retest the repaired combat in Tacet 1; leave its stamina reward alone."""
    from src.task.TacetTask import TacetTask
    from src.task.WWOneTimeTask import WWOneTimeTask
    tacet=task.get_task_by_class(TacetTask)
    WWOneTimeTask.run(tacet)
    tacet.ensure_main(time_out=60)
    tacet.openF2Book('gray_book_boss')
    before,_,_=tacet.get_stamina()
    if type(before) is not int or before<0:raise RuntimeError('无法读取体力，未进入免费战斗复测')
    try:
        tacet.open_boss_book('wuyin')
        tacet.teleport_to_tacet(0)
        tacet.click_team_challenge()
        tacet.wait_in_team_and_world(time_out=120)
        if not tacet.wait_until(lambda:tacet.in_combat(target=True),time_out=30,
                                raise_if_not_found=False,post_action=lambda:tacet.click()):
            raise RuntimeError('无音区没有进入真实战斗')
        tacet.screenshot('validation-tacet-combat-ready')
        save(validation_scene='combat_tacet',validation_scene_ready=True,
             validation_stamina_before=before,validation_reward_claim_allowed=False)
        yield
    finally:
        tacet.ensure_main(time_out=60)
        tacet.openF2Book('gray_book_boss')
        after,_,_=tacet.get_stamina()
        tacet.screenshot('validation-tacet-stamina-after')
        tacet.ensure_main(time_out=60)
        save(validation_stamina_after=after,validation_zero_stamina_spent=(type(after) is int and 0<=after-before<=2))
        if type(after) is not int or not 0<=after-before<=2:
            raise RuntimeError('免费战斗复测的体力回查不一致，请查看截图')


@contextmanager
def phone_dialog_scene(task,save):
    """Open the observed NPC Feixun icon; leave the reply to AutoDialogTask."""
    task.ensure_main(time_out=60)
    task.send_key_down('alt')
    try:
        task.click_relative(.217,.049,after_sleep=1)
    finally:
        task.send_key_up('alt')
    try:
        task.screenshot('validation-phone-opened')
        task.wait_ocr(.01,0,.70,.18,match=re.compile(r'^飞讯$'),time_out=5,raise_if_not_found=True)
        # The current game opens the contact list, rather than a thread.
        # Use the observed event promoter, not a random story contact.
        task.wait_click_ocr(.15,.12,.30,.22,match=re.compile(r'无音消除.*宣传员'),
                            time_out=5,raise_if_not_found=True,after_sleep=.7)
        task.wait_click_ocr(.14,.23,.30,.30,match=re.compile(r'消除.*消除'),
                            time_out=5,raise_if_not_found=True,after_sleep=1)
        def pending_reply():
            return task.find_one('message',horizontal_variance=.15) and task.find_one('message_dialog',vertical_variance=.4,horizontal_variance=.2)
        ready=task.wait_until(pending_reply,time_out=20,raise_if_not_found=False)
        task.screenshot('validation-phone-before')
        if not ready:
            raise RuntimeError('当前飞讯没有待处理NPC对话，未选择玩家聊天或推进其他任务')
        task._validation_phone_text=phone_dialog_text(task)
        if not task._validation_phone_text:raise RuntimeError('飞讯内容不可读，未运行对话辅助')
        save(validation_scene='dialog_phone',validation_scene_ready=True,
             validation_dialog_before=task._validation_phone_text)
        yield
    finally:
        task.ensure_main(time_out=60)


def prepare_current_echo(task,save):
    """Resume only the audited interrupted +10 Rocksteady Guardian."""
    task.sleep(2)
    task.wait_until(lambda:task.find_echo_enhance() or task.ocr(.09,.12,.30,.18,match=re.compile(r'^磐石守卫$')),
                    time_out=15,raise_if_not_found=True)
    if task.find_echo_enhance():
        if not task.ocr(.68,.10,.92,.17,match=re.compile(r'^磐石守卫$')) or task.read_selected_level()!=10:
            raise RuntimeError('背包当前选中候选与中断记录不一致，未改选声骸')
        task.click(task.find_echo_enhance(),after_sleep=1)
    # A material picker lists the inventory to the right. Close only that
    # panel; do not blindly press Escape on the cultivation screen itself.
    if task.ocr(.73,.89,.97,.96,match='基础经验排序'):
        task.send_key('esc',after_sleep=1)
    name=task.ocr(.09,.12,.30,.18,match=re.compile(r'^磐石守卫$'))
    level=task.ocr(.10,.18,.15,.22,match=re.compile(r'^\+10$'))
    if len(name)!=1 or len(level)!=1:
        task.screenshot('resume-candidate-mismatch')
        raise RuntimeError('当前界面不是中断的+10磐石守卫，未选择其他候选或消耗材料')
    if task.ocr(.10,.54,.22,.62,match=re.compile(r'^不限$')):
        task.click_relative(.50,.60,after_sleep=.3)
    from src.task.EnhanceEchoTask import property_pattern,number_pattern
    from src.task.echo_stats import pair_stats
    texts=task.ocr(.09,.3,.40,.53)
    properties=[p for p in task.find_boxes(texts,match=property_pattern) if '辅音' not in p.name]
    stats=pair_stats(properties,task.find_boxes(texts,match=number_pattern))
    if stats!=[('防御百分比','12.8%'),('生命','580')]:
        raise RuntimeError('当前候选副词条与中断记录不一致，未继续强化')
    staged=task.ocr(.22,.61,.30,.69,match='清除')
    if staged:task.click(staged,after_sleep=.3)
    elif not task.find_add_mat():
        raise RuntimeError('当前放入区域状态未知，未继续强化')
    task.screenshot('enhance-resume-same-candidate')
    save(resumed_source_run='enhance-20261029-023100-232',resumed_level=10,resumed_stats=stats)
