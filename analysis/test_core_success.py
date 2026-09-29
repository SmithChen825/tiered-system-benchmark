import unittest
import numpy as np
from core_success import wilson, exact_paired_p, holm


class CoreStatisticsTests(unittest.TestCase):
    def test_zero_success_interval_is_not_zero_width(self):
        low, high = wilson(0,36)
        self.assertAlmostEqual(low,0)
        self.assertAlmostEqual(high,0.0964186285944637)

    def test_perfect_success_interval(self):
        low, high = wilson(36,36)
        self.assertAlmostEqual(high,1)
        self.assertAlmostEqual(low,1-wilson(0,36)[1])

    def test_task_permutation_boundaries(self):
        self.assertEqual(exact_paired_p([0]*12),1)
        self.assertEqual(exact_paired_p([3]*12),2/4096)
        self.assertEqual(exact_paired_p([1,-1]+[0]*10),1)

    def test_holm_monotonicity_and_original_order(self):
        np.testing.assert_allclose(holm([.04,.001,.03]),[.06,.003,.06])


if __name__ == '__main__':
    unittest.main()
