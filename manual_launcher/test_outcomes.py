import unittest
from outcomes import echo_outcome, farm_outcome, assist_outcome, daily_outcome

class EchoOutcomeTests(unittest.TestCase):
    def result(self,errors,**kwargs):
        evidence=dict(pickups=1,observed_combats=1,requested_rounds=1,returned_to_main=True);evidence.update(kwargs)
        return echo_outcome(errors,**evidence)
    def test_known_end_transition_requires_combat_pickup_and_return_evidence(self):
        for message in ('BaseCombatTask:not in_team while switching ',
                        'BaseCombatTask:combat check not in combat ',
                        'BaseCombatTask:sleep check not in combat ',
                        'CombatCheck:target_enemy failed, try recheck break out of combat '):
            result=self.result([message]);self.assertEqual(result['status'],'EXECUTION_FINISHED')
            self.assertEqual(result['recovered_log_errors'],[message])
            for missing in ({'pickups':0},{'observed_combats':0},{'returned_to_main':False},{'requested_rounds':2}):
                with self.subTest(message=message,missing=missing):self.assertEqual(self.result([message],**missing)['status'],'NEEDS_REVIEW')
    def test_other_failures_are_not_cleared_by_a_successful_pickup(self):
        errors=['BaseCombatTask:not in_team while switching','capture surface lost']
        result=self.result(errors);self.assertEqual(result['errors'],['capture surface lost'])
        self.assertEqual(result['status'],'NEEDS_REVIEW');self.assertEqual(errors[0],'BaseCombatTask:not in_team while switching')
    def test_similar_or_revive_failure_logs_remain_errors(self):
        for message in ('BaseCombatTask:reset to false failed: not in_team while switching','BaseCombatTask:failed switch chars'):
            self.assertEqual(self.result([message])['errors'],[message])


class FarmOutcomeTests(unittest.TestCase):
    def result(self,errors=(),**updates):
        evidence=dict(before=132,after=92,spent=40,budget=40,reward_claims=1,returned_to_main=True)
        evidence.update(updates)
        return farm_outcome(list(errors),**evidence)

    def test_verified_reward_and_return_can_resolve_known_combat_end_messages(self):
        result=self.result(['BaseCombatTask:sleep check not in combat ',
                            'CombatCheck:target_enemy failed, try recheck break out of combat '])
        self.assertEqual(result['status'],'FARM_PASSED')
        self.assertEqual(len(result['recovered_log_errors']),2)

    def test_missing_evidence_never_becomes_success(self):
        for missing in ({'after':132},{'after':91},{'spent':0},{'budget':80},{'reward_claims':0},
                        {'returned_to_main':False},{'pending_claim':{'cost':40}}):
            with self.subTest(missing=missing):
                self.assertEqual(self.result(['BaseCombatTask:sleep check not in combat'],**missing)['status'],'NEEDS_REVIEW')

    def test_other_errors_survive_verified_consumption(self):
        result=self.result(['capture surface lost','BaseCombatTask:sleep check not in combat'])
        self.assertEqual(result['status'],'NEEDS_REVIEW')
        self.assertEqual(result['errors'],['capture surface lost'])


class AssistOutcomeTests(unittest.TestCase):
    def test_only_completed_helper_sessions_recover_known_transitions(self):
        errors=['BaseCombatTask:sleep check not in combat']
        self.assertEqual(assist_outcome(errors,completed_combat_sessions=1,normal_ending=True)['status'],'ASSIST_FINISHED')
        for sessions,normal in ((0,True),(1,False)):
            self.assertEqual(assist_outcome(errors,completed_combat_sessions=sessions,normal_ending=normal)['status'],'NEEDS_REVIEW')

    def test_skill_or_capture_failures_are_never_hidden(self):
        errors=['Hiyuki:clicked liberation but no effect','capture lost']
        self.assertEqual(assist_outcome(errors,completed_combat_sessions=1,normal_ending=True)['errors'],errors)


class DailyOutcomeTests(unittest.TestCase):
    def result(self,errors=(),**updates):
        evidence=dict(initial_points=0,final_points=140,execution_completed=True,returned_to_main=True)
        evidence.update(updates)
        return daily_outcome(list(errors),**evidence)

    def test_completed_daily_and_readback_can_resolve_known_end_transitions(self):
        result=self.result(['BaseCombatTask:sleep check not in combat'])
        self.assertEqual(result['status'],'READBACK_PASSED')
        self.assertTrue(result['daily_completed'])
        self.assertEqual(len(result['recovered_log_errors']),1)

    def test_partial_or_missing_daily_evidence_never_becomes_a_pass(self):
        for missing in ({'final_points':80},{'execution_completed':False},{'returned_to_main':False},
                        {'pending_claim':{'cost':60}},{'initial_points':140},{'final_points':True}):
            with self.subTest(missing=missing):self.assertEqual(self.result(**missing)['status'],'NEEDS_REVIEW')

    def test_daily_completion_keeps_skill_and_capture_failures_visible(self):
        errors=['Hiyuki:clicked liberation but no effect','capture lost']
        self.assertEqual(self.result(errors)['errors'],errors)

if __name__=='__main__':unittest.main(verbosity=2)
