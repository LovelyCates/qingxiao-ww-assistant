import time

from ok import FindFeature, Logger
from ok import TriggerTask
from src.scene.WWScene import WWScene
from src.task.BaseWWTask import BaseWWTask, f_white_color

logger = Logger.get_logger(__name__)
NON_PICKUP_ACTIONS = ('离开副本','退出副本','Leave Domain','Exit Domain')


class AutoPickTask(TriggerTask, BaseWWTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "🌸 Auto Pick"
        self.description = "Auto Pick Flowers in Game World"
        self.default_config.update({
            '_enabled': True,
            'Pick Up White List': ['吸收', 'Absorb'],
            'Pick Up Black List': ['开始合成', '领取奖励', 'Claim', '合成台', '开始烹饪']
        })

    def send_fs(self):
        # One input per observation; the next run must reacquire the frame,
        # world state and interaction label before sending another F.
        self.send_key('f')
        self.sleep(0.35)

    def run(self):
        if not self.scene.in_team(self.in_team_and_world):
            return
        start = time.time()
        while time.time() - start < 1:
            f = self.find_one('pick_up_f_hcenter_vcenter', box=self.f_search_box,
                              threshold=0.8)
            if not f:
                return
            percent = self.calculate_color_percentage(f_white_color, f)
            if percent < 0.5:
                self.log_debug(f'f white color percent: {percent} wait')
                self.next_frame()
                continue
            interaction_row = f.copy(x_offset=f.width * 2, width_offset=f.width * 16,
                                     height_offset=f.height * 2, y_offset=-f.height)
            if self.find_one('pick_up_xinyao_well', box=interaction_row, threshold=0.8):
                return False
            dialog_search = f.copy(x_offset=f.width * 3, width_offset=f.width * 2, height_offset=f.height * 2,
                                   y_offset=-f.height,
                                   name='search_dialog')

            # Read only the active F row. Searching several rows can find an
            # allowed item below a reward/NPC and press F on the wrong target.
            text_area = f.copy(x_offset=f.width * 5.2, width_offset=f.width * 9,
                               height_offset=f.height * 0.8, y_offset=-f.height * 0.4)
            texts = self.ocr(box=text_area)
            label = ''.join(box.name.strip() for box in texts).casefold()
            if not label:
                return False
            blocked = [*NON_PICKUP_ACTIONS,*(self.config.get('Pick Up Black List') or [])]
            if any(word.casefold() in label for word in blocked):
                return False
            dialog_3_dots = self.find_feature('dialog_3_dots', box=dialog_search,
                                              threshold=0.6)

            if dialog_3_dots:
                if self.config.get('Pick Up White List'):
                    if any(word.casefold() == label for word in self.config.get('Pick Up White List')):
                        logger.info(f'found Pick Up White List {f}')
                        self.send_fs()
                        return True
            else:
                self.send_fs()
                return True
            self.next_frame()
