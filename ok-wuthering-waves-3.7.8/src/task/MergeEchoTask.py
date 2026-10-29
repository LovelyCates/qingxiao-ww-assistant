import re

from src.Labels import Labels
from src.task.BaseWWTask import BaseWWTask

FULL_BATCH_PATTERN = re.compile(r"(?<!\d)100\s*/\s*100(?!\d)")
MATERIAL_COUNT_PATTERN = re.compile(r'^已选择融合材料[（(]\s*(\d+)\s*/\s*(\d+)[）)]$')
QUALITY_WARNING_PATTERN = re.compile(r'^消耗材料中包含品质较高的声骸[，,]?请确认是否继续[？?]?$')


def parse_material_count(labels):
    counts = [MATERIAL_COUNT_PATTERN.fullmatch(re.sub(r'\s+', '', label)) for label in labels]
    counts = [m for m in counts if m]
    if len(counts) != 1:
        raise RuntimeError('无法唯一识别已选择融合材料数量，已停止')
    selected, limit = map(int, counts[0].groups())
    if limit != 100 or not 0 <= selected <= limit:
        raise RuntimeError('融合材料数量或上限异常，已停止')
    return selected


class MergeEchoTask(BaseWWTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "♻️ Merge Discarded Echoes"
        self.description = (
            "Must have 1000 discarded Echo to Run, "
            "Merge discarded Echoes in full batches of 100."
        )
        self.notify_if_not_enough = True

    def run(self):
        self.ensure_main()
        hotkey = self.key_config.get("Bag Key", "b")
        self.send_key(hotkey)
        if not self.wait_until(
                lambda: not self.in_team_and_world(),
                time_out=5,
                raise_if_not_found=False,
        ):
            self.log_error(
                f"can not open bag with hotkey {hotkey}",
                notify=True,
            )
            return
        self.sleep(3)

        if self.has_discard_merge_dialog():
            self.click_dialog_left_button()
            self.sleep(2)
            self.click_relative(0.034, 0.293, after_sleep=1)
            self.click_relative(0.580, 0.911, after_sleep=4)
        else:
            if self.notify_if_not_enough:
                self.log_error(
                    "Must have 1000 discarded Echo to Run",
                    notify=True,
                )
            self.ensure_main()
            return

        self.merge_echoes()

    def has_discard_merge_dialog(self):
        return bool(self.find_one([
            Labels.cancel_button_hcenter_vcenter,
            Labels.cancel_button_highlight_hcenter_vcenter,
        ]))

    def inspect_merge_filter(self):
        """Set and verify the discarded-only filter, without submitting materials."""
        self.discard_filter_verified = False
        self.ensure_main()
        self.open_esc_menu()
        self.wait_click_ocr(match='数据坞', box='right', raise_if_not_found=True, settle_time=0.2)
        self.wait_ocr(match='数据坞', box='top_left', raise_if_not_found=True, settle_time=0.2)
        self.click_relative(0.04, 0.56, after_sleep=0.5)
        self.wait_click_ocr(0.52, 0.08, 0.70, 0.17, match='标准融合', raise_if_not_found=True,
                            settle_time=0.2, after_sleep=0.5)
        self.wait_click_ocr(0.35, 0.83, 0.75, 0.98, match=re.compile(r'^(批量融合|标准融合)$'), raise_if_not_found=True,
                            settle_time=0.2, after_sleep=1)
        self.screenshot('merge-preflight-batch-page')
        self.click_relative(0.04, 0.91, after_sleep=0.5)
        self.wait_ocr(0.65, 0.0, 0.98, 0.12, match='筛选', raise_if_not_found=True, settle_time=0.2)
        self.screenshot('merge-preflight-filter')
        self.wait_click_ocr(0.65, 0.79, 0.98, 0.88, match='重置', raise_if_not_found=True,
                            settle_time=0.2, after_sleep=0.5)
        self.wait_click_ocr(0.67, 0.17, 0.77, 0.24, match=re.compile(r'^已[弃棄]置$'),
                            raise_if_not_found=True, settle_time=0.2, after_sleep=0.5)
        self.screenshot('merge-preflight-discard-filter')
        labels = [box.name for box in self.ocr(0.65, 0.12, 0.98, 0.86)]
        if self.read_discard_filter_state() != (True, False, False):
            raise RuntimeError('未确认只勾选已弃置，已停止；不会选择或提交材料')
        self.click_relative(0.943, 0.06, after_sleep=0.5)
        self.wait_ocr(0.67, 0.80, 0.97, 0.89, match=MATERIAL_COUNT_PATTERN,
                      raise_if_not_found=True, settle_time=0.2)
        if self.read_material_count() != 0:
            raise RuntimeError('融合页面存在先前选择，已停止，请先取消材料选择')
        self.require_discard_filter_chip()
        self.discard_filter_verified = True
        self.screenshot('merge-preflight-ready')
        return labels

    def read_discard_filter_state(self):
        labels = {b.name.replace('棄', '弃') for b in self.ocr(0.67, 0.17, 0.97, 0.24)}
        if not {'已弃置', '已锁定', '未标记'} <= labels:
            raise RuntimeError('无法识别三种声骸状态筛选，已停止')
        states = []
        # Inner discs only: avoid the bright outline shared by all radio buttons.
        for x in (0.7505, 0.8490, 0.9486):
            pixels = self.box_of_screen(x-.002, .201, x+.002, .207).crop_frame(self.frame)
            if pixels.size == 0:
                raise RuntimeError('筛选状态图像为空，已停止')
            bright = (pixels[:, :, :3].min(axis=2) > 145).mean()
            if bright >= .75:
                states.append(True)
            elif bright <= .10:
                states.append(False)
            else:
                raise RuntimeError('筛选勾选状态不明确，已停止')
        return tuple(states)

    def require_discard_filter_chip(self):
        if not self.ocr(.02, .83, .20, .89, match=re.compile(r'^已[弃棄]置$')):
            raise RuntimeError('已弃置筛选标签消失，已停止；不会提交材料')

    def read_material_count(self):
        return parse_material_count([b.name for b in self.ocr(.67, .80, .97, .89)])

    def select_discarded_batch(self):
        if not getattr(self, 'discard_filter_verified', False):
            raise RuntimeError('尚未验证弃置筛选，已停止')
        self.require_discard_filter_chip()
        if self.read_material_count() != 0:
            raise RuntimeError('材料选择未清空，已停止，避免重复操作')
        self.wait_click_ocr(.23, .89, .31, .95, match='全选', raise_if_not_found=True,
                            settle_time=.2, after_sleep=1)
        self.screenshot('merge-selected-materials')
        return self.read_material_count()

    def merge_echoes(self):
        self.open_merge_page()
        while self.merge_full_batch():
            pass

        self.ensure_main()

    def open_merge_page(self):
        self.inspect_merge_filter()

    def merge_full_batch(self):
        if getattr(self, 'merge_result_visible', False):
            self.open_merge_page()
            self.merge_result_visible = False
        selected = self.select_discarded_batch()
        if selected < 100:
            self.log_info("All full batches of discarded Echoes have been merged.")
            return False
        self.require_discard_filter_chip()
        if self.read_material_count() != 100:
            raise RuntimeError('提交前材料数量变化，已停止')
        self.pending_merge_count = 100
        self.wait_click_ocr(.70, .88, .91, .96, match='标准融合', raise_if_not_found=True,
                            settle_time=.2, after_sleep=1)
        self.screenshot('merge-after-submit')
        self.confirm_verified_merge_warning()
        self.wait_ocr(match='获得声骸', box='top', time_out=8,
                      raise_if_not_found=True, settle_time=.5)
        self.screenshot('merge-observed-result')
        self.pending_merge_count = None
        self.merge_result_visible = True
        return True

    def confirm_verified_merge_warning(self):
        # Only the quality warning belonging to our verified full batch is
        # accepted. Leave "do not remind again" unchanged for later operations.
        warning = self.wait_ocr(.25, .40, .75, .51, match=QUALITY_WARNING_PATTERN,
                                time_out=2, settle_time=.2)
        if not warning:
            return False
        if not getattr(self, 'discard_filter_verified', False) or getattr(self, 'pending_merge_count', None) != 100:
            raise RuntimeError('融合确认缺少本次筛选和材料数量证据，已停止')
        self.screenshot('merge-quality-confirmation')
        self.wait_click_ocr(.56, .58, .76, .68, match=re.compile(r'^确认$'),
                            raise_if_not_found=True, settle_time=.2, after_sleep=1)
        return True
