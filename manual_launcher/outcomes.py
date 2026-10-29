"""Classify only a narrowly identified, recovered combat-end observation."""
def echo_outcome(errors,*,pickups,observed_combats,requested_rounds,returned_to_main):
    recovered=[];pending=[]
    proved=(returned_to_main is True and type(pickups) is int and pickups>0
            and type(observed_combats) is int and observed_combats>=requested_rounds)
    handled_end_messages={'BaseCombatTask:not in_team while switching',
                          'BaseCombatTask:combat check not in combat',
                          'BaseCombatTask:sleep check not in combat',
                          'CombatCheck:target_enemy failed, try recheck break out of combat'}
    for message in errors:
        if proved and message.strip() in handled_end_messages:recovered.append(message)
        else:pending.append(message)
    return {'status':'NEEDS_REVIEW' if pending else 'EXECUTION_FINISHED',
            'errors':pending,'recovered_log_errors':recovered}


def farm_outcome(errors,*,before,after,spent,budget,reward_claims,returned_to_main,pending_claim=None):
    proved=(all(type(value) is int for value in (before,after,spent,budget,reward_claims))
            and 0 < spent == budget <= before and reward_claims>0
            and returned_to_main is True and pending_claim is None
            and 0 <= after-(before-spent) <= 1)
    handled={'BaseCombatTask:combat check not in combat',
             'BaseCombatTask:sleep check not in combat',
             'CombatCheck:target_enemy failed, try recheck break out of combat'}
    recovered=[message for message in errors if proved and message.strip() in handled]
    pending=[message for message in errors if not (proved and message.strip() in handled)]
    return dict(status='FARM_PASSED' if proved and not pending else 'NEEDS_REVIEW',
                errors=pending,recovered_log_errors=recovered,consumption_verified=proved)


def assist_outcome(errors,*,completed_combat_sessions,normal_ending):
    proved=normal_ending is True and type(completed_combat_sessions) is int and completed_combat_sessions>0
    handled={'BaseCombatTask:combat check not in combat','BaseCombatTask:sleep check not in combat',
             'CombatCheck:target_enemy failed, try recheck break out of combat'}
    recovered=[message for message in errors if proved and message.strip() in handled]
    pending=[message for message in errors if not (proved and message.strip() in handled)]
    return dict(status='ASSIST_FINISHED' if not pending else 'NEEDS_REVIEW',
                errors=pending,recovered_log_errors=recovered)


def daily_outcome(errors,*,initial_points,final_points,execution_completed,returned_to_main,pending_claim=None):
    proved=(type(initial_points) is int and 0<=initial_points<100
            and type(final_points) is int and 100<=final_points<=999
            and execution_completed is True and returned_to_main is True and pending_claim is None)
    handled={'BaseCombatTask:combat check not in combat','BaseCombatTask:sleep check not in combat',
             'CombatCheck:target_enemy failed, try recheck break out of combat'}
    recovered=[m for m in errors if proved and m.strip() in handled]
    pending=[m for m in errors if not (proved and m.strip() in handled)]
    return dict(status='READBACK_PASSED' if proved and not pending else 'NEEDS_REVIEW',
                errors=pending,recovered_log_errors=recovered,
                daily_completed=type(final_points) is int and final_points>=100)
