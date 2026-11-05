import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock
from system_stats import SystemSampler, cpu_counters, memory_usage, storage_usage


class SystemStatsTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.proc = Path(self.folder.name)
        self.now = 10
        self.disk = Mock(return_value=SimpleNamespace(f_frsize=4096, f_bsize=4096, f_blocks=1000, f_bfree=300, f_bavail=250))
        self.sampler = SystemSampler(self.proc, clock=lambda: self.now, statvfs=self.disk)
        self.stat('100 0 50 850 0 0 0 0 30 0')
        (self.proc/'meminfo').write_text('MemTotal: 10000 kB\nMemFree: 1000 kB\nMemAvailable: 4000 kB\nCached: 3000 kB\n')

    def stat(self, counters):
        (self.proc/'stat').write_text('cpu ' + counters + '\ncpu0 1 2 3 4\n')

    def test_guest_not_counted_twice_and_total_normalized_across_cores(self):
        first = self.sampler.sample()
        self.assertIsNone(first.cpu)
        self.assertTrue(first.reset_history)
        self.now += 2
        self.stat('120 0 55 915 10 0 0 0 45 0')
        second = self.sampler.sample()
        self.assertEqual(second.cpu, 25.0)
        self.assertFalse(second.reset_history)
        self.assertEqual(cpu_counters('cpu 1 2 3 4'), (1,2,3,4,0,0,0,0))

    def test_ram_uses_available_not_just_free(self):
        memory = self.sampler.sample().memory
        self.assertEqual(memory.percent, 60)
        self.assertEqual(memory.available, 4000*1024)
        self.assertEqual(memory.used, 6000*1024)

    def test_disk_reserved_space_and_thirty_second_cadence(self):
        first = self.sampler.sample().storage
        self.assertEqual(first.percent, 70)
        self.assertEqual(first.available, 250*4096)
        for _ in range(14):
            self.now += 2
            self.sampler.sample()
        self.assertEqual(self.disk.call_count, 1)
        self.now += 2
        self.sampler.sample()
        self.assertEqual(self.disk.call_count, 2)

    def test_suspend_counter_reset_and_hidden_restart_reprime(self):
        self.sampler.sample()
        self.now += 100
        self.stat('200 0 100 1700 0 0 0 0')
        self.assertIsNone(self.sampler.sample().cpu)
        self.now += 2
        self.stat('201 0 100 1709 0 0 0 0')
        self.assertEqual(self.sampler.sample().cpu, 10)
        self.now += 2
        self.stat('100 0 50 850 0 0 0 0')
        self.assertTrue(self.sampler.sample().reset_history)
        self.sampler.reset()
        self.assertIsNone(self.sampler.sample().cpu)

    def test_failures_are_independent_and_recover(self):
        self.sampler.sample()
        (self.proc/'stat').unlink()
        (self.proc/'meminfo').write_text('MemTotal: 100 kB\n')
        bad = self.sampler.sample()
        self.assertIsNone(bad.cpu)
        self.assertIsNone(bad.memory)
        self.assertEqual(set(bad.errors), {'cpu', 'memory'})
        self.assertIsNotNone(bad.storage)
        self.disk.side_effect = OSError('Filesystem unavailable')
        self.now += 30
        self.assertIsNone(self.sampler.sample().storage)
        self.disk.side_effect = None
        self.now += 30
        self.assertIsNotNone(self.sampler.sample().storage)

    def test_invalid_and_zero_counters_never_become_fake_usage(self):
        for source in ('', 'cpu0 1 2 3 4', 'cpu -1 0 0 0', 'cpu x 0 0 0'):
            with self.assertRaises(ValueError):
                cpu_counters(source)
        for source in ('MemTotal: 0 kB\nMemAvailable: 0 kB', 'MemTotal: 10 MB\nMemAvailable: 5 kB', 'MemTotal: 10 kB\nMemAvailable: 20 kB'):
            with self.assertRaises(ValueError):
                memory_usage(source)
        self.sampler.sample()
        self.now += 2
        self.assertIsNone(self.sampler.sample().cpu)
        self.disk.return_value.f_blocks = 0
        with self.assertRaises(ValueError):
            storage_usage(self.disk.return_value)


if __name__ == '__main__':
    unittest.main()
