import asyncio
import pytest
from backend.collector import Collector


def test_collector_sample():
    async def _test():
        is_mode = False
        collector = Collector(mode_provider=lambda: is_mode)

        sample = await asyncio.to_thread(collector._sample_system)
        assert "timestamp" in sample
        assert "cpu" in sample
        assert "memory" in sample
        assert "disk" in sample
        assert "psi" in sample
        assert "mode_enabled" in sample
        assert sample["mode_enabled"] is False

        assert 0.0 <= sample["cpu"]["total_percent"] <= 100.0
        assert 0.0 <= sample["memory"]["percent"] <= 100.0

    asyncio.run(_test())


def test_collector_subscription():
    async def _test():
        collector = Collector()
        q = collector.subscribe()

        sample = {"test": 123}
        collector._broadcast(sample)

        received = await asyncio.wait_for(q.get(), timeout=1.0)
        assert received == sample

        collector.unsubscribe(q)
        assert q not in collector._subscribers

    asyncio.run(_test())


def test_collector_lifecycle():
    async def _test():
        collector = Collector()
        await collector.start()
        assert collector._running is True

        # Allow one tick to collect
        await asyncio.sleep(1.2)
        latest = collector.get_latest_sample()
        assert latest is not None
        assert len(collector.get_history()) >= 1

        await collector.stop()
        assert collector._running is False

    asyncio.run(_test())
