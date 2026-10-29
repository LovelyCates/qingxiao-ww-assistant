"""Read the activity value, whose reward threshold is not its maximum value."""
import re

ACTIVITY_NUMBER = re.compile(r'^\d{1,3}$')


def parse_daily_activity(labels):
    values = [int(text.strip()) for text in labels if ACTIVITY_NUMBER.fullmatch(text.strip())]
    if len(values) != 1:
        raise ValueError('无法唯一识别日常活跃度，已停止；不会按0活跃继续刷取')
    # The game keeps adding points after the final reward at 100 (for example
    # 140 in the captured live fixture). Preserve the actual displayed value.
    return values[0]


def read_daily_activity(task):
    boxes = task.ocr(0.19, 0.8, 0.30, 0.93, match=ACTIVITY_NUMBER)
    try:
        return parse_daily_activity([box.name for box in boxes])
    except ValueError:
        task.screenshot('activity-unreadable')
        raise


def read_weekly_progress(task):
    """Read the current score above the bar, excluding reward denominators."""
    readings=[];observations=[]
    import cv2
    for scale in (2,3):
        def enlarge_digits(image):
            # The game's outlined gold zeroes are read as decimal punctuation
            # at native size. Upscale the isolated score, preserving its text.
            hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
            mask=cv2.inRange(hsv,(15,80,110),(45,255,255))
            mask=cv2.resize(mask,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
            return cv2.cvtColor(255-mask,cv2.COLOR_GRAY2BGR)
        labels=[box.name.strip() for box in task.ocr(.188,.825,.275,.889,frame_processor=enlarge_digits)]
        observations.append(labels)
        values=[int(label) for label in labels if re.fullmatch(r'\d{1,4}',label)]
        if len(values)==1 and 0 <= values[0] <= 6000:readings.append(values[0])
    if len(readings)!=2 or len(set(readings))!=1:
        task.screenshot('weekly-progress-unreadable')
        raise ValueError(f'周游历值未获得两次一致的有效读数：{observations}')
    return readings[0]
