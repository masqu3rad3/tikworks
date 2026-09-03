"""Unit tests for tik.core.benchmark module."""

import pytest

from tik.core.benchmark import BenchmarkResult, Benchmark, _BenchmarkContext
from tik.maya.core.benchmark import MayaBenchmark


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_result_with_empty_times(self):
        """Test BenchmarkResult properties when times list is empty."""
        result = BenchmarkResult(name="empty_test", iterations=0, times=[])
        assert result.total == 0.0
        assert result.average == 0.0
        assert result.best == 0.0
        assert result.worst == 0.0
        assert result.stdev == 0.0

    def test_result_with_single_time(self):
        """Test BenchmarkResult properties with single measurement."""
        result = BenchmarkResult(name="single_test", iterations=1, times=[0.5])
        assert result.total == 0.5
        assert result.average == 0.5
        assert result.best == 0.5
        assert result.worst == 0.5
        assert result.stdev == 0.0  # Single value has 0 stdev

    def test_result_with_multiple_times(self):
        """Test BenchmarkResult properties with multiple measurements."""
        times = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = BenchmarkResult(name="multi_test", iterations=5, times=times)
        assert result.total == pytest.approx(1.5)
        assert result.average == pytest.approx(0.3)
        assert result.best == pytest.approx(0.1)
        assert result.worst == pytest.approx(0.5)
        assert result.stdev > 0  # Multiple values have positive stdev

    def test_str_representation_milliseconds(self):
        """Test __str__ formats correctly in milliseconds for small times."""
        times = [0.001, 0.002, 0.003]
        result = BenchmarkResult(name="ms_test", iterations=3, times=times)
        str_repr = str(result)
        assert "BENCHMARK: ms_test" in str_repr
        assert "Iterations : 3" in str_repr
        assert "ms" in str_repr

    def test_str_representation_seconds(self):
        """Test __str__ formats correctly in seconds for large times."""
        times = [1.5, 2.0, 2.5]
        result = BenchmarkResult(name="sec_test", iterations=3, times=times)
        str_repr = str(result)
        assert "BENCHMARK: sec_test" in str_repr
        assert "Average" in str_repr
        # Should be in seconds, not milliseconds
        assert " s\n" in str_repr


class TestBenchmark:
    """Tests for Benchmark class."""

    def test_benchmark_initialization(self):
        """Test Benchmark initializes with empty results dict."""
        benchmark = Benchmark()
        assert benchmark.results == {}

    def test_measure_returns_context(self):
        """Test measure() returns a _BenchmarkContext instance."""
        benchmark = Benchmark()
        context = benchmark.measure("test_context", iterations=5, warmup=1)
        assert isinstance(context, _BenchmarkContext)
        assert context.name == "test_context"
        assert context.iterations == 5
        assert context.warmup == 1

    def test_compare_with_no_results(self, capsys):
        """Test compare() prints message when no results exist."""
        benchmark = Benchmark()
        benchmark.compare()
        captured = capsys.readouterr()
        assert "No results to compare." in captured.out

    def test_compare_with_results(self, capsys):
        """Test compare() prints comparison table with results."""
        benchmark = Benchmark()
        # Add some mock results
        benchmark.results["test_a"] = BenchmarkResult(
            name="test_a", iterations=5, times=[0.1, 0.2]
        )
        benchmark.results["test_b"] = BenchmarkResult(
            name="test_b", iterations=5, times=[0.05, 0.1]
        )
        benchmark.compare()
        captured = capsys.readouterr()
        assert "COMPARISON REPORT" in captured.out
        assert "test_a" in captured.out
        assert "test_b" in captured.out


class TestBenchmarkContext:
    """Tests for _BenchmarkContext class."""

    def test_context_manager_enter_exit(self):
        """Test context manager enter and exit methods."""
        benchmark = Benchmark()
        context = benchmark.measure("context_test")
        with context as ctx:
            assert ctx is context
        # No exception should be raised

    def test_run_executes_function(self):
        """Test run() executes function the specified number of times."""
        benchmark = Benchmark()
        call_count = 0

        def dummy_function():
            nonlocal call_count
            call_count += 1

        context = benchmark.measure("run_test", iterations=3, warmup=2)
        result = context.run(dummy_function)

        # warmup (2) + iterations (3) = 5 total calls
        assert call_count == 5
        assert len(result.times) == 3
        assert result.name == "run_test"
        assert "run_test" in benchmark.results

    def test_run_with_args_and_kwargs(self):
        """Test run() passes arguments to the function."""
        benchmark = Benchmark()
        captured_args = []

        def func_with_args(arg_val, kwarg_val=None):
            captured_args.append((arg_val, kwarg_val))

        context = benchmark.measure("args_test", iterations=2, warmup=1)
        context.run(func_with_args, "positional", kwarg_val="keyword")

        # warmup (1) + iterations (2) = 3 calls
        assert len(captured_args) == 3
        for arg_val, kwarg_val in captured_args:
            assert arg_val == "positional"
            assert kwarg_val == "keyword"

    def test_run_restores_gc_state(self):
        """Test run() restores garbage collection state after execution."""
        import gc

        benchmark = Benchmark()
        gc_was_enabled = gc.isenabled()

        context = benchmark.measure("gc_test", iterations=1, warmup=0)
        context.run(lambda: None)

        # GC state should be restored
        assert gc.isenabled() == gc_was_enabled

    def test_run_restores_gc_on_exception(self):
        """Test run() restores GC state even when function raises exception."""
        import gc

        benchmark = Benchmark()
        gc_was_enabled = gc.isenabled()

        def raising_func():
            raise ValueError("Test exception")

        context = benchmark.measure("exception_test", iterations=3, warmup=0)
        with pytest.raises(ValueError, match="Test exception"):
            context.run(raising_func)

        # GC state should still be restored
        assert gc.isenabled() == gc_was_enabled


class TestMayaBenchmark:
    """Tests for MayaBenchmark class (Maya-specific benchmarking)."""

    def test_maya_benchmark_initialization(self):
        """Test MayaBenchmark initializes correctly."""

        benchmark = MayaBenchmark()
        assert benchmark.results == {}
        assert isinstance(benchmark, Benchmark)

    def test_measure_returns_context_with_new_scene_attr(self):
        """Test measure() returns context with _new_scene attribute."""
        benchmark = MayaBenchmark()
        context = benchmark.measure("test", iterations=2, warmup=1, new_scene=True)
        assert hasattr(context, "_new_scene")
        assert context._new_scene is True

    def test_run_disables_and_restores_undo(self):
        """Test run() disables undo during benchmark and restores afterwards."""
        from maya import cmds

        benchmark = MayaBenchmark()
        undo_states = []

        def capture_undo_state():
            undo_states.append(cmds.undoInfo(q=True, state=True))

        # Ensure undo is enabled before
        cmds.undoInfo(state=True)
        assert cmds.undoInfo(q=True, state=True) is True

        context = benchmark.measure("undo_test", iterations=2, warmup=0)
        context.run(capture_undo_state)

        # Undo should have been disabled during runs
        assert all(state is False for state in undo_states)
        # Undo should be restored after
        assert cmds.undoInfo(q=True, state=True) is True

    def test_run_with_new_scene_creates_fresh_scene(self):
        """Test run() creates new scene before each iteration when new_scene=True."""
        from maya import cmds

        benchmark = MayaBenchmark()
        node_counts = []

        def count_transforms():
            # Count user-created transforms (excluding default cameras)
            transforms = cmds.ls(type="transform")
            # Create a node to verify scene reset
            cmds.createNode("transform", name="benchmarkTestNode")
            node_counts.append(len(transforms))

        context = benchmark.measure(
            "new_scene_test", iterations=3, warmup=0, new_scene=True
        )
        context.run(count_transforms)

        # Each iteration should start with similar base count
        # (default scene transforms like persp, top, etc.)
        # If scene wasn't reset, counts would increase
        assert node_counts[0] == node_counts[1] == node_counts[2]

    def test_run_without_new_scene_preserves_scene_state(self):
        """Test run() preserves scene state when new_scene=False."""
        from maya import cmds

        benchmark = MayaBenchmark()
        cmds.file(new=True, force=True)
        node_counts = []

        def count_and_create():
            transforms = cmds.ls(type="transform")
            node_counts.append(len(transforms))
            cmds.createNode("transform", name="persistNode#")

        context = benchmark.measure(
            "preserve_scene_test", iterations=3, warmup=0, new_scene=False
        )
        context.run(count_and_create)

        # Without scene reset, node count should increase
        assert node_counts[0] < node_counts[1] < node_counts[2]

    def test_run_stores_results(self):
        """Test run() stores results in parent benchmark."""
        benchmark = MayaBenchmark()

        def dummy_func():
            pass

        context = benchmark.measure("result_test", iterations=2, warmup=1)
        result = context.run(dummy_func)

        assert "result_test" in benchmark.results
        assert benchmark.results["result_test"] is result
        assert result.iterations == 2
        assert len(result.times) == 2

