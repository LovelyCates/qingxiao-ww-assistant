import unittest
from local_runner import daily_stamina_budget


class DailyBudget(unittest.TestCase):
    def test_tacet_cannot_spend_240_when_only_180_are_needed(self):
        self.assertEqual(daily_stamina_budget(240, 60), 180)
        self.assertEqual(daily_stamina_budget(343, 60), 180)

    def test_forty_cost_domains_can_reach_the_180_daily_objective(self):
        self.assertEqual(daily_stamina_budget(240, 40), 200)
        self.assertEqual(daily_stamina_budget(180, 40), 160)

    def test_insufficient_stamina_never_creates_a_spendable_claim(self):
        self.assertEqual(daily_stamina_budget(59, 60), 0)
        self.assertEqual(daily_stamina_budget(163, 60), 120)
