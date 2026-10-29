"""Finite saved-login-list inventory; never submits login or removes accounts."""
import re

def read_saved_accounts(task):
    from src.task.MultiAccountDailyTask import combo_items
    from .accounts import account_key
    if combo:=task._login_combo():
        labels=combo_items(combo)
    else:
        task._target_account_key=None
        task.next_frame()
        labels=[box.name for box in task.ocr() if re.search(r'\*{2,}|@',box.name)]
        # Focus changes commonly collapse the SDK dropdown. Open it and read
        # the same fresh frame with the game's existing elevated interaction.
        if len(set(labels))<=1:
            closed=task.do_find_account_drop_down()
            if not closed:
                task.screenshot('account-list-unrecognized')
                raise RuntimeError('未识别到已保存账号下拉框；没有点击登录。')
            task.click(closed,after_sleep=2)
            task.next_frame()
            labels=[box.name for box in task.ocr() if re.search(r'\*{2,}|@',box.name)]
    unique={}
    for label in labels:
        try:key=account_key(label)
        except ValueError:continue
        unique.setdefault(key,label)
    task.screenshot('saved-account-list')
    if not unique:raise RuntimeError('账号列表没有可读标识；没有登录或删除任何账号。')
    return list(unique.values())
