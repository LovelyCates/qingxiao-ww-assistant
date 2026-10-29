"""Bounded frame evidence for the explicit combat validation scene only."""
from pathlib import Path
import time
try:
    from .model import atomic_json
except ImportError:
    from model import atomic_json


class LiberationProbe:
    def __init__(self,task,run_directory,limit=12):
        self.task=task
        self.path=Path(run_directory)/'liberation-observations.json'
        self.limit=limit
        self.attempt=0
        self.rows=[]

    def __call__(self,stage,char):
        if stage=='ready':self.attempt+=1
        if not 0<self.attempt<=self.limit:return
        name=f'liberation-{self.attempt}-{type(char).__name__}-{stage}'
        self.task.screenshot(name)
        self.rows.append(dict(attempt=self.attempt,stage=stage,char=type(char).__name__,
            index=char.index,at=time.time(),cooldowns={str(k):dict(v) for k,v in self.task.cds.items()}))
        atomic_json(self.path,self.rows)
