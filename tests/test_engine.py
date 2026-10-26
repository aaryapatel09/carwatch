import unittest

from engine import ActivityEngine

IN = (0.4, 0.3, 0.6, 0.8)
OUT = (0.8, 0.3, 1.0, 0.8)


class Rules(unittest.TestCase):
    def test_linger_once(self):
        e = ActivityEngine(dwell=2)
        self.assertEqual(e.update(0, [(1, IN)]), [])
        self.assertEqual(e.update(1, [(1, IN)]), [])
        self.assertEqual(e.update(2, [(1, IN)])[0]["kind"], "lingering")
        self.assertEqual(e.update(3, [(1, IN)]), [])

    def test_missing_does_not_count_as_dwell(self):
        e = ActivityEngine(dwell=2)
        e.update(0, [(1, IN)])
        self.assertEqual(e.update(10, [(1, IN)]), [])

    def test_repeat(self):
        e = ActivityEngine()
        for t in range(4):
            self.assertEqual(e.update(t, [(1, IN if t % 2 == 0 else OUT)]), [])
        self.assertEqual(e.update(4, [(1, IN)])[0]["kind"], "repeated_approach")

    def test_passersby(self):
        e = ActivityEngine(dwell=2)
        for t in range(10):
            self.assertEqual(e.update(t, [(t, IN)]), [])

    def test_window_expires(self):
        e = ActivityEngine(window=2)
        e.update(0, [(1, IN)])
        e.update(1, [(1, OUT)])
        self.assertEqual(e.update(5, [(1, IN)]), [])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            ActivityEngine(zone=(0.8, 0, 0.2, 1))
        e = ActivityEngine()
        e.update(2, [])
        with self.assertRaises(ValueError):
            e.update(1, [])


if __name__ == "__main__":
    unittest.main()
