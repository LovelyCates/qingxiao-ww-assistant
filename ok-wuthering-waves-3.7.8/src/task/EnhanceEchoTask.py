# EnhanceEchoTask.py
import re
import time
import os

from ok import FindFeature, Logger
from ok.feature.Box import get_bounding_box
from ok.util.file import clear_folder
from src.scene.WWScene import WWScene
from src.task.BaseWWTask import BaseWWTask
from src.task.echo_stats import EchoRecognitionError, pair_stats, parse_number

logger = Logger.get_logger(__name__)

number_pattern = re.compile(r"^[\d.%％ ]+$")
property_pattern = re.compile(r"[\u4e00-\u9fff]{2,}")


class EnhanceEchoTask(BaseWWTask, FindFeature):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "⬆️ 批量强化声骸(游戏与okww语言必须为简体/繁体中文)"
        self.description = "点击B进入背包, 在过滤器中选择需要强化的声骸, 并按照等级从0排序后开始."
        self.fail_reason = ""
        self.supported_languages = ["zh_CN", "zh_TW"]
        self.default_config.update({
            '必须有双爆': True,
            '双爆出现之前必须全有效词条': True,
            '双爆总计>=': 13.8,
            '首条双爆>=': 6.9,
            '有效词条>=': 3,
            '第一条必须为有效词条': True,
            '有效词条': ['暴击', '暴击伤害', '攻击百分比'],
            'Pause after Success': True,
        })
        self.config_type["有效词条"] = {'type': "multi_selection",
                                        'options': ['暴击伤害', '暴击', '攻击百分比', '生命百分比', '防御百分比',
                                                    '攻击', '生命', '防御',
                                                    '共鸣效率', '普攻伤害加成',
                                                    '重击伤害加成', '共鸣解放伤害加成',
                                                    '共鸣技能伤害加成']}
        self.config_description = {
            '必须有双爆': '如果开启，声骸最终必须同时拥有暴击和暴击伤害。如果剩余孔位不足以凑齐双爆，则丢弃',
            '双爆出现之前必须全有效词条': '开启后，在暴击或暴击伤害词条出现之前，前面的所有词条必须都在有效词条列表中',
            '双爆总计>=': '当声骸同时存在暴击和爆伤时，需要满足 暴击 + (爆伤/2) >= 此数值',
            '首条双爆>=': '仅检查第一条出现的暴击或暴击伤害是否满足条件, 爆伤/2',
            '有效词条>=': '声骸满级时需达到的有效词条数量，若剩余孔位无法凑齐该数量，则停止强化并丢弃',
            '第一条必须为有效词条': '如果开启，第一个副词条必须在有效词条列表中且符合数值要求，否则直接丢弃',
            '有效词条': '定义哪些属性被视为有效',
            'Pause after Success': 'When a success occurs, send notification and pause task',
        }

    def find_echo_enhance(self):
        return self.ocr(0.82, 0.86, 0.97, 0.96, match='培养')

    def is_0_level(self):
        return self.read_selected_level() == 0

    def read_selected_level(self):
        # Both the old card and the current 3.7 detail panel are supported.
        # Restrict OCR to their level labels, never the inventory grid.
        levels = []
        for rect in ((0.90, 0.225, 0.96, 0.27), (0.69, 0.18, 0.73, 0.215)):
            levels.extend(self.ocr(*rect, match=re.compile(r'^\+\s*\d{1,2}$'), target_height=2160))
        if len(levels) != 1:
            raise EchoRecognitionError('无法唯一识别当前声骸等级，已停止，请检查背包声骸页')
        level = int(levels[0].name.replace('+', '').strip())
        if not 0 <= level <= 25:
            raise EchoRecognitionError('声骸等级超出范围，已停止')
        return level

    def select_0_level_echo(self):
        # 3.7 起从培养界面返回后, 背包选中并滚动到刚强化的声骸, 不再停在第一格
        self.click(0.13, 0.21, after_sleep=0.5)  # 第一格
        if self.is_0_level():
            return True
        for _ in range(2):  # 升降序切换两次, 列表回到顶部
            self.click(0.35, 0.917, after_sleep=0.5)
        self.click(0.13, 0.21, after_sleep=0.5)
        return self.is_0_level()

    def run(self):
        self.info_set('成功声骸数量', 0)
        self.info_set('失败声骸数量', 0)
        self.prepare_evidence()
        while True:
            enhance = self.find_echo_enhance()
            if not enhance:
                raise Exception('必须在背包声骸界面过滤后开始!')
            if not self.select_0_level_echo():
                total = self.info_get('成功声骸数量') + self.info_get('失败声骸数量')
                if self.debug:
                    self.screenshot('无可强化声骸')
                self.log_info(f'无可强化声骸, 任务结束! 强化{total}个, 符合条件{self.info_get("成功声骸数量")}个',
                              notify=True)
                if self.info_get('成功声骸数量') >= 1:
                    try:
                        self.open_evidence()
                    except Exception as e:
                        self.log_error(f"无法打开截图文件夹: {e}")
                return
            start = time.time()
            while time.time() - start < 5:
                if enhance:
                    self.click(enhance, after_sleep=0.5)
                enhance = self.find_echo_enhance()
                if not enhance:
                    break

            self.enhance_selected_echo()

    def enhance_selected_echo(self, expected_stats=1):
        self.ensure_stage_settings()
        self.ensure_material_quality()
        while True:
            add_mat = self.find_add_mat()
            if not add_mat:
                self.ensure_stage_settings()
                add_mat=self.find_add_mat()
                if not add_mat:raise Exception('强化设置未切换为阶段放入，已停止')
            self.click(add_mat, after_sleep=0.3)

            if not self.wait_click_ocr(0.1, 0.88, 0.29, 0.96, match=['强化并调谐'],
                                       settle_time=0.1,
                                       after_sleep=1.5):
                self.screenshot('enhance-submit-unavailable')
                if self.ocr(0.17, 0.88, 0.29, 0.96, match=['强化']):
                    raise Exception('阶段放入未达到下一调谐等级，已停止且未提交；请核对经验材料库存与界面状态')
                else:
                    raise Exception('找不到 强化并调谐!')
            dialog_deadline = time.monotonic() + 15
            while handle := self.wait_ocr(0.24, 0.18, 0.75, 0.98,
                                          match=[re.compile('不再提示'), '调谐成功', re.compile('点击任')],
                                          time_out=2):
                if time.monotonic() >= dialog_deadline:
                    raise EchoRecognitionError('强化结果提示未退出，已停止后续操作')
                if handle[0].name in ['本次登录不再提示', '本次登入不再提示']:
                    self.click_skip_dialog_confirm()
                elif handle[0].name in ['点击任意位置返回', '调谐成功']:
                    self.click(handle, after_sleep=1)
                else:
                    self.sleep(0.5)
            self.sleep(0.1)
            decision = self.read_stat_decision(expected_stats)
            if not decision:
                self.trash_and_esc()
                break

            if expected_stats == 5:
                self.lock_and_esc()
                break
            expected_stats += 1

    def prepare_evidence(self):
        clear_folder('screenshots')

    def open_evidence(self):
        os.startfile(os.path.abspath('screenshots'))

    def read_stat_decision(self, expected_stats):
        previous = None
        reason = '词条读数未稳定'
        for _ in range(4):
            self.next_frame()
            texts = self.ocr(0.09, 0.3, 0.40, 0.53)
            properties = [p for p in self.find_boxes(texts, match=property_pattern) if '辅音' not in p.name]
            values = self.find_boxes(texts, match=number_pattern)
            try:
                paired = pair_stats(properties, values)
                if len(paired) != expected_stats:
                    raise EchoRecognitionError(f'本阶段应有{expected_stats}条词条，实际识别{len(paired)}条')
                if paired == previous:
                    self.info_set('属性', properties)
                    self.info_set('值', values)
                    return self.check_echo_stats(properties, values)
                previous = paired
            except EchoRecognitionError as exc:
                reason = str(exc)
                previous = None
            self.sleep(.25)
        self.screenshot('enhance-recognition-uncertain')
        raise EchoRecognitionError(reason + '；已停止，不会弃置或继续消耗')

    def find_confirm(self):
        button_box = self.box_of_screen(0.60, 0.65, 0.82, 0.82)
        if confirm := self.find_one('echo_enhance_confirm', box=button_box, threshold=0.7):
            return [confirm]
        return self.ocr(box=button_box, match='确认')

    def check_echo_stats(self, properties, values):
        self.fail_reason = ""
        invalid_count = 0

        paired_stats = pair_stats(properties, values)

        total_count = len(paired_stats)

        crit_rate_val = 0
        crit_dmg_val = 0
        has_crit_rate = False
        has_crit_dmg = False

        checked_first_crit = False
        has_encountered_crit = False

        valid_stats = self.config.get('有效词条') or []

        for p_raw, v_str in paired_stats:
            p = p_raw
            if '暴击伤害' in p:
                p = '暴击伤害'
            elif '暴击' in p:
                p = '暴击'
            elif '攻击' in p:
                p = '攻击' + ('百分比' if '%' in v_str or '％' in v_str else '')
            elif '生命' in p:
                p = '生命' + ('百分比' if '%' in v_str or '％' in v_str else '')
            elif '防御' in p:
                p = '防御' + ('百分比' if '%' in v_str or '％' in v_str else '')
            elif '效率' in p:
                p = '共鸣效率'
            elif '普攻' in p:
                p = '普攻伤害加成'
            elif '重击' in p:
                p = '重击伤害加成'
            elif '解放' in p:
                p = '共鸣解放伤害加成'
            elif '技能' in p:
                p = '共鸣技能伤害加成'

            v = parse_number(v_str)

            is_valid_prop = True
            is_crit_stat = p in ['暴击', '暴击伤害']

            if self.config.get(
                    '双爆出现之前必须全有效词条') and '暴击' in valid_stats and '暴击伤害' in valid_stats and not has_encountered_crit:
                if not is_crit_stat:
                    if p not in valid_stats:
                        self.fail_reason = f'双爆前含无效_{p}'
                        self.log_info(f'双爆出现前存在无效词条 {p}, 丢弃')
                        return False
                else:
                    has_encountered_crit = True

            if is_valid_prop and p not in valid_stats:
                is_valid_prop = False
                self.log_debug(f'非有效词条, {p} 不符合条件')

            if p == '暴击':
                has_crit_rate = True
                crit_rate_val += v
                if '暴击' in valid_stats and not checked_first_crit:
                    checked_first_crit = True
                    if v < self.config.get('首条双爆>='):
                        self.fail_reason = f'首条暴击不足_{v}'
                        self.log_info(f'首条暴击 {v} < {self.config.get("首条双爆>=")}，丢弃')
                        return False

            elif p == '暴击伤害':
                has_crit_dmg = True
                crit_dmg_val += v
                if '暴击伤害' in valid_stats and not checked_first_crit:
                    checked_first_crit = True
                    if v / 2 < self.config.get('首条双爆>='):
                        self.fail_reason = f'首条爆伤不足_{v}'
                        self.log_info(f'首条爆伤 {v} < {self.config.get("首条双爆>=")}，丢弃')
                        return False

            if not is_valid_prop:
                invalid_count += 1

        self.info_set('不符合条件属性', invalid_count)

        if self.config.get('必须有双爆'):
            missing_crit = (0 if has_crit_rate else 1) + (0 if has_crit_dmg else 1)
            remaining_slots = 5 - total_count
            if remaining_slots < missing_crit:
                self.fail_reason = f'无法凑齐双爆_缺{missing_crit}'
                self.log_info(f'无法凑齐双爆 (缺{missing_crit}种, 剩{remaining_slots}孔), 丢弃')
                return False

        if has_crit_rate and has_crit_dmg:
            total_score = crit_rate_val + (crit_dmg_val / 2)
            if total_score < self.config.get('双爆总计>='):
                self.fail_reason = f'双爆总计不足_{total_score:.1f}'
                self.log_info(f'双爆总计 {total_score:.1f} < {self.config.get("双爆总计>=")}，丢弃')
                return False

        if total_count == 1 and self.config.get('第一条必须为有效词条') and invalid_count == 1:
            self.fail_reason = '首条无效'
            self.log_info('第一条必须为有效词条, 丢弃')
            return False

        valid_count = total_count - invalid_count
        remaining_slots = 5 - total_count
        if (valid_count + remaining_slots) < self.config.get('有效词条>='):
            self.fail_reason = f'有效词条不足_上限{valid_count + remaining_slots}'
            self.log_info(f'剩余孔位不足以达到设定的有效词条数量, 丢弃')
            return False

        return True

    def find_add_mat(self):
        return self.wait_ocr(0.09, 0.6, 0.38, 0.86, match=['阶段放入'], time_out=1)

    def ensure_material_quality(self):
        # The quality filter is independent of the material-only setting.
        # A four-star cap can exhaust purple EXP mid-stage while gold EXP
        # remains available, leaving an ordinary unsynchronised action.
        quality=self.ocr(.10,.61,.23,.69,match=re.compile(r'不限|[一二三四五]星及以下道具'))
        if not quality:
            raise EchoRecognitionError('无法确认经验材料品质筛选，未继续放入')
        if len(quality)!=1:
            raise EchoRecognitionError('经验材料品质筛选不唯一，未继续放入')
        if quality[0].name!='不限':
            self.click(quality,after_sleep=.3)
            self.screenshot('enhance-quality-options')
            self.wait_click_ocr(.10,.54,.22,.62,match=re.compile(r'^不限$'),
                                raise_if_not_found=True,after_sleep=.3)
            if not self.ocr(.10,.61,.23,.69,match=re.compile(r'^不限$')):
                raise EchoRecognitionError('未确认经验材料不限品质筛选，未继续放入')
        self.screenshot('enhance-quality-verified')

    def read_auto_settings(self):
        states=[]
        for x,y in ((.862,.3315),(.862,.5125),(.4725,.654)):
            image=self.box_of_screen(x-.006,y-.009,x+.006,y+.009).crop_frame(self.frame)
            if image.size==0:raise EchoRecognitionError('自动放入设置图像为空，未放入材料')
            states.append(float((image[:,:,:3].min(axis=2)<150).mean())>=.15)
        return tuple(states)

    def ensure_stage_settings(self):
        self.click_relative(.331,.647,after_sleep=.5)
        self.wait_ocr(.05,.07,.30,.16,match='自动放入设置',raise_if_not_found=True)
        self.screenshot('enhance-settings-before')
        self.wait_click_ocr(.52,.25,.86,.41,match=re.compile(r'^阶段放入$'),raise_if_not_found=True,after_sleep=.3)
        self.wait_click_ocr(.52,.47,.86,.56,match=re.compile(r'^开启同步调谐$'),raise_if_not_found=True,after_sleep=.3)
        self.wait_click_ocr(.12,.60,.47,.69,match=re.compile(r'^仅强化材料$'),raise_if_not_found=True,after_sleep=.3)
        self.next_frame()
        if self.read_auto_settings()!=(True,True,True):
            self.screenshot('enhance-settings-uncertain')
            self.wait_click_ocr(.47,.80,.65,.89,match=re.compile(r'^取消$'),raise_if_not_found=True)
            raise EchoRecognitionError('未确认阶段放入、同步调谐和仅强化材料，未放入材料')
        self.screenshot('enhance-settings-verified')
        self.wait_click_ocr(.70,.80,.88,.89,match=re.compile(r'^确认$'),raise_if_not_found=True,after_sleep=.5)
        # The disabled action still says "强化" before any materials are
        # staged. Validate "强化并调谐" after staging, before submitting it.

    def esc(self):
        start = time.time()
        while not self.find_echo_enhance() and time.time() - start < 10:
            self.send_key('esc', interval=4, after_sleep=0.2)
        self.sleep(0.1)

    def trash_and_esc(self):
        start = time.time()
        success = False
        drop_status_box = get_bounding_box([
            self.get_box_by_name('echo_dropped'),
            self.get_box_by_name('echo_not_dropped'),
        ]).scale(1.05)
        while time.time() - start < 5:
            drop_status = self.find_best_match_in_box(drop_status_box,
                                                      ['echo_dropped', 'echo_not_dropped'], threshold=0.7)
            if not drop_status:
                raise Exception('无法找到声骸弃置状态!')
            if drop_status.name == 'echo_not_dropped':
                self.send_key('z', after_sleep=1)
            else:
                self.log_info('成功弃置!')
                success = True
                break
        if not success:
            raise Exception('弃置失败!')
        self.info_incr('失败声骸数量')
        safe_reason = re.sub(r'[<>:"/\\|?*]', '', self.fail_reason)
        self.screenshot_echo(f'failed/{self.info_get("失败声骸数量")}_{safe_reason}')
        self.esc()
        self.log_info('不符合条件 丢弃')
        self.wait_ocr(0.82, 0.86, 0.97, 0.96, match='培养', settle_time=0.1)

    def screenshot_echo(self, name):
        echo = self.box_of_screen(0.09, 0.09, 0.37, 0.55).crop_frame(self.frame)
        self.screenshot(name=name, frame=echo)

    def lock_and_esc(self):
        start = time.time()
        success = False
        lock_status_box = get_bounding_box([
            self.get_box_by_name('echo_locked'),
            self.get_box_by_name('echo_not_locked'),
        ]).scale(1.05)
        while time.time() - start < 5:
            drop_status = self.find_best_match_in_box(lock_status_box,
                                                      ['echo_locked', 'echo_not_locked'], threshold=0.7)
            if not drop_status:
                raise Exception('无法找到声骸上锁状态!')
            if drop_status.name == 'echo_not_locked':
                self.send_key('c', after_sleep=1)
            else:
                self.log_info('成功上锁!')
                success = True
                break
        if not success:
            raise Exception('上锁失败!')
        self.info_incr('成功声骸数量')
        self.screenshot_echo(f'success/{self.info_get("成功声骸数量")}')
        self.log_info('成功并上锁')
        if self.config.get('Pause after Success'):
            self.log_info('符合条件的声骸，已暂停任务', notify=True)
            self.pause()
        self.esc()
        self.wait_ocr(0.82, 0.86, 0.97, 0.96, match='培养', settle_time=0.1)


