import time
import statistics
import functools
import inspect
from typing import Callable, Any, List, Dict, Optional, Tuple, Union
import matplotlib.pyplot as plt
from tqdm import tqdm

class Benchmark:
    """
    A utility class for benchmarking function performance.
    
    This class allows measuring execution time of functions with customizable
    number of runs, warm-up iterations, and provides detailed statistics
    and optional visualization.
    """
    
    def __init__(self, 
                 name: str = "Benchmark",
                 runs: int = 5, 
                 warmup_runs: int = 1,
                 show_progress: bool = True):
        """
        Initialize a benchmark instance.
        
        Args:
            name: Name of the benchmark for reporting
            runs: Number of times to run the function for timing
            warmup_runs: Number of warm-up runs (not included in timing)
            show_progress: Whether to show progress bar during runs
        """
        self.name = name
        self.runs = runs
        self.warmup_runs = warmup_runs
        self.show_progress = show_progress
        self.results = []
        
    def run(self, func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """
        Run the benchmark on a function.
        
        Args:
            func: The function to benchmark
            *args: Positional arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            Dictionary with benchmark results
        """
        func_name = func.__name__
        print(f"Benchmarking {func_name}...")
        
        if self.warmup_runs > 0:
            if self.show_progress:
                print(f"Performing {self.warmup_runs} warm-up run(s)...")
                warm_iter = tqdm(range(self.warmup_runs), desc="Warm-up")
            else:
                warm_iter = range(self.warmup_runs)
                
            for _ in warm_iter:
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    print(f"Error during warm-up: {e}")
                    return {"error": str(e)}
        
        timing_results = []
        
        if self.show_progress:
            run_iter = tqdm(range(self.runs), desc="Benchmark runs")
        else:
            run_iter = range(self.runs)
            
        for _ in run_iter:
            try:
                start_time = time.time()
                result = func(*args, **kwargs)
                end_time = time.time()
                elapsed_time = end_time - start_time
                timing_results.append(elapsed_time)
            except Exception as e:
                print(f"Error during benchmark run: {e}")
                return {"error": str(e)}
        
        stats = {
            "function": func_name,
            "runs": self.runs,
            "mean": statistics.mean(timing_results),
            "median": statistics.median(timing_results),
            "min": min(timing_results),
            "max": max(timing_results),
            "total": sum(timing_results)
        }
        
        if len(timing_results) > 1:
            stats["stdev"] = statistics.stdev(timing_results)
        
        self.results.append({
            "function": func_name,
            "stats": stats,
            "raw_timings": timing_results
        })
        
        self._print_results(stats)
        
        return stats
    
    def _print_results(self, stats: Dict[str, Any]) -> None:
        """Print formatted benchmark results."""
        print("\n" + "=" * 50)
        print(f"Benchmark results for {stats['function']}")
        print("-" * 50)
        print(f"Number of runs: {stats['runs']}")
        print(f"Mean time:      {stats['mean']:.6f} seconds")
        print(f"Median time:    {stats['median']:.6f} seconds")
        print(f"Min time:       {stats['min']:.6f} seconds")
        print(f"Max time:       {stats['max']:.6f} seconds")
        print(f"Total time:     {stats['total']:.6f} seconds")
        
        if "stdev" in stats:
            print(f"Std deviation:  {stats['stdev']:.6f} seconds")
        
        print("=" * 50 + "\n")
        
    def compare(self, funcs: List[Tuple[Callable, dict]], 
                labels: Optional[List[str]] = None,
                plot: bool = True) -> Dict[str, Any]:
        """
        Compare multiple functions with the same benchmark parameters.
        
        Args:
            funcs: List of (function, kwargs) tuples to benchmark
            labels: Optional list of labels for the functions
            plot: Whether to generate comparison plots
            
        Returns:
            Dictionary with comparison results
        """
        if labels is None:
            labels = [f[0].__name__ for f in funcs]
        
        self.results = []
        
        for (func, kwargs), label in zip(funcs, labels):
            print(f"\nBenchmarking {label}...")
            self.run(func, **kwargs)
        
        comparison = {
            "benchmark_name": self.name,
            "runs": self.runs,
            "functions": labels,
            "mean_times": [r["stats"]["mean"] for r in self.results],
            "median_times": [r["stats"]["median"] for r in self.results],
            "min_times": [r["stats"]["min"] for r in self.results],
            "max_times": [r["stats"]["max"] for r in self.results]
        }
        
        print("\n" + "=" * 60)
        print(f"BENCHMARK COMPARISON: {self.name}")
        print("=" * 60)
        print(f"{'Function':<20} {'Mean (s)':<12} {'Median (s)':<12} {'Min (s)':<12} {'Max (s)':<12}")
        print("-" * 60)
        
        for i, label in enumerate(labels):
            print(f"{label:<20} {comparison['mean_times'][i]:<12.6f} "
                  f"{comparison['median_times'][i]:<12.6f} "
                  f"{comparison['min_times'][i]:<12.6f} "
                  f"{comparison['max_times'][i]:<12.6f}")
        
        print("=" * 60)
        
        if plot:
            self._create_comparison_plots(comparison)
        
        return comparison
    
    def _create_comparison_plots(self, comparison: Dict[str, Any]) -> None:
        """Create comparison plots for benchmark results."""
        try:
            plt.figure(figsize=(10, 6))
            
            plt.subplot(1, 2, 1)
            plt.bar(comparison["functions"], comparison["mean_times"])
            plt.title("Mean Execution Time")
            plt.ylabel("Time (seconds)")
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            
            plt.subplot(1, 2, 2)
            data = [r["raw_timings"] for r in self.results]
            plt.boxplot(data, labels=comparison["functions"])
            plt.title("Execution Time Distribution")
            plt.ylabel("Time (seconds)")
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            
            plt.subplots_adjust(bottom=0.3)
            plt.savefig(f"{self.name.replace(' ', '_')}_comparison.png")
            plt.close()
            
            print(f"\nComparison plot saved as '{self.name.replace(' ', '_')}_comparison.png'")
            
        except Exception as e:
            print(f"Error creating plots: {e}")

def benchmark(runs: int = 5, 
              warmup_runs: int = 1, 
              show_progress: bool = True,
              name: Optional[str] = None) -> Callable:
    """
    Decorator for benchmarking functions.
    
    Args:
        runs: Number of times to run the function for timing
        warmup_runs: Number of warm-up runs (not included in timing)
        show_progress: Whether to show progress bar during runs
        name: Custom name for the benchmark
        
    Returns:
        Decorated function that runs benchmark
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            benchmark_name = name if name else f"Benchmark_{func.__name__}"
            
            bench = Benchmark(
                name=benchmark_name,
                runs=runs,
                warmup_runs=warmup_runs,
                show_progress=show_progress
            )
            
            stats = bench.run(func, *args, **kwargs)
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


if __name__ == "__main__":
    def slow_function(n=1000000):
        """A deliberately slow function for testing."""
        result = 0
        for i in range(n):
            result += i
        return result
    
    def faster_function(n=1000000):
        """A faster version of the same calculation."""
        return sum(range(n))
    
    bench = Benchmark(name="Simple Test", runs=3, warmup_runs=1)
    bench.run(slow_function, 500000)
    
    @benchmark(runs=3, name="Decorated Function Test")
    def test_function():
        return slow_function(300000)
    
    result = test_function()
    
    bench = Benchmark(name="Function Comparison", runs=3)
    bench.compare(
        funcs=[
            (slow_function, {"n": 500000}),
            (faster_function, {"n": 500000})
        ],
        labels=["Slow Implementation", "Fast Implementation"],
        plot=True
    )