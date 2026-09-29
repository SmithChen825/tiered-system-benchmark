import unittest
from secondary_outcomes import quantiles,ratio

class SecondaryTests(unittest.TestCase):
    def test_no_successes_is_missing_not_zero(self):
        self.assertEqual(quantiles([]),dict(n=0,median=None,q1=None,q3=None))
    def test_zero_requests_precision_undefined(self):
        self.assertIsNone(ratio(0,0))
        self.assertEqual(ratio(0,33),0)
    def test_linear_quantiles(self):
        self.assertEqual(quantiles([1,2,3,10]),dict(n=4,median=2.5,q1=1.75,q3=4.75))

if __name__=='__main__':
    unittest.main()
