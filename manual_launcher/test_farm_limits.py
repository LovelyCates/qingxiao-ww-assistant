import unittest
from model import make_request


class FarmLimits(unittest.TestCase):
    def test_each_domain_can_reserve_stamina_for_other_validation_runs(self):
        for action,cost in (('tacet',60),('forgery',40),('simulation',40)):
            request=make_request(action,stamina_limit=cost)
            self.assertEqual(request['StaminaLimit'],cost)

    def test_invalid_limits_cannot_reach_game(self):
        for action,value in (('tacet',40),('forgery',60),('simulation',True),('daily',180),
                             ('tacet',0),('forgery',280),('simulation','40')):
            with self.subTest(action=action,value=value),self.assertRaises(ValueError):
                make_request(action,stamina_limit=value)

    def test_existing_requests_keep_their_original_budget_behavior(self):
        self.assertNotIn('StaminaLimit',make_request('tacet'))

    def test_explicit_nest_target_limit_leaves_full_run_default_available(self):
        self.assertEqual(make_request('nightmare',target_limit=1)['TargetLimit'],1)
        self.assertNotIn('TargetLimit',make_request('nightmare'))
        for action,value in (('nightmare',True),('nightmare',0),('nightmare',101),('echo',1)):
            with self.subTest(action=action,value=value),self.assertRaises(ValueError):
                make_request(action,target_limit=value)
