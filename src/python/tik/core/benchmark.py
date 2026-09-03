from __future__ import annotations

import gc
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, Optional


# --- Data Container ---
@dataclass
class BenchmarkResult:
    name: str
    iterations: int
    times: list[float] = field(default_factory=list)

    @property
    def total(self):
        return sum(self.times)

    @property
    def average(self):
        return statistics.mean(self.times) if self.times else 0.0

    @property
    def best(self):
        return min(self.times) if self.times else 0.0

    @property
    def worst(self):
        return max(self.times) if self.times else 0.0

    @property
    def stdev(self):
        """Standard Deviation helps you see how consistent the run was."""
        if len(self.times) > 1:
            return statistics.stdev(self.times)
        return 0.0

    def __str__(self):
        # Dynamic formatting for readability (ms vs seconds)
        unit = "s"
        mult = 1.0
        if self.average < 1.0:
            unit = "ms"
            mult = 1000.0

        return (
            f"BENCHMARK: {self.name}\n"
            f"{'-' * 40}\n"
            f"Iterations : {self.iterations}\n"
            f"Total Time : {self.total:.4f} s\n"
            f"Average    : {self.average * mult:.4f} {unit}\n"
            f"Best       : {self.best * mult:.4f} {unit}\n"
            f"Worst      : {self.worst * mult:.4f} {unit}\n"
            f"StDev      : {self.stdev * mult:.4f} {unit}\n"
            f"{'=' * 40}"
        )


# --- The Engine ---
class Benchmark:
    def __init__(self):
        self.results: dict[str, BenchmarkResult] = {}

    def measure(self, name: str, iterations: int = 10, warmup: int = 2):
        """Measure a block of code, as a context manager or a decorator.

        Example::

            with benchmark.measure("My Test", iterations=50):
                do_something()
        """
        return _BenchmarkContext(self, name, iterations, warmup)

    def compare(self):
        """Prints a comparison table of all stored results."""
        if not self.results:
            print("No results to compare.")
            return

        print(f"\n{'COMPARISON REPORT':^60}")
        print(f"{'=' * 60}")
        print(f"{'Name':<25} | {'Avg (ms)':<10} | {'Total (s)':<10} | {'Best':<10}")
        print(f"{'-' * 60}")

        # Sort by average time (fastest first)
        sorted_results = sorted(
            self.results.values(), key=lambda result: result.average
        )

        for res in sorted_results:
            print(
                f"{res.name:<25} | {res.average * 1000:<10.4f} | "
                f"{res.total:<10.4f} | {res.best * 1000:<10.4f}"
            )
        print(f"{'=' * 60}\n")


class _BenchmarkContext:
    def __init__(self, parent: Benchmark, name: str, iterations: int, warmup: int):
        self.parent = parent
        self.name = name
        self.iterations = iterations
        self.warmup = warmup
        self._func: Optional[Callable] = None

    def __enter__(self):
        # We can't easily loop *inside* a `with` block for the user logic
        # without using a callback.
        # This generic enter returns a 'runner' helper if the user wants manual control,
        # but the Cleaner approach is to use this class to wrap a callable.
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def run(self, func: Callable, *args, **kwargs):
        """
        Executes the function multiple times, handling GC and Warmup.
        """
        times = []

        # Warmup (Run without timing to load caches/compile)
        # Disable GC during run to prevent spikes (optional but recommended for pure
        # algos)
        gc_old = gc.isenabled()
        gc.disable()

        try:
            for _ in range(self.warmup):
                func(*args, **kwargs)

            # Actual Benchmark
            for _ in range(self.iterations):
                t0 = time.perf_counter()
                func(*args, **kwargs)
                t1 = time.perf_counter()
                times.append(t1 - t0)

        finally:
            if gc_old:
                gc.enable()

        # Store Results
        result = BenchmarkResult(self.name, self.iterations, times)
        self.parent.results[self.name] = result
        print(result)  # Immediate feedback
        return result
