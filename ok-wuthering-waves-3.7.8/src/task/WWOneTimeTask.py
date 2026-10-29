from ok import BrowserInteraction, PostMessageInteraction
from src.task.MouseResetTask import MouseResetTask


class WWOneTimeTask:

    def run(self):
        # Match upstream v3.7.12: an interrupted rotation must not make the
        # first startup sleep fail before a new task can enter the game.
        if hasattr(self, 'reset_combat_state'):
            self.reset_combat_state('onetime task start')
        mouse_reset_task = self.executor.get_task_by_class(MouseResetTask)
        mouse_reset_task.run()
        if isinstance(self.executor.interaction, PostMessageInteraction):
            self.executor.interaction.activate()
        self.sleep(0.5)
