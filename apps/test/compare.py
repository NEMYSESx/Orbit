import matplotlib.pyplot as plt

indexed_times = [0.0214 + 0.001 * i for i in range(100)]  # Simulated variation
brute_times = [0.5368 + 0.005 * ((-1)**i) * (i % 3) for i in range(100)]  # Slight variation


fig, axs = plt.subplots(1, 2, figsize=(12, 6))

axs[0].bar(
    ['HNSW Indexed Search (Top 5)', 'Brute Force Search (Top 5)'],
    [sum(indexed_times)/len(indexed_times), sum(brute_times)/len(brute_times)]
)
axs[0].set_title('Mean Execution Time')
axs[0].set_ylabel('Time (seconds)')
axs[0].tick_params(axis='x', rotation=45)

axs[1].boxplot([indexed_times, brute_times], labels=['HNSW Indexed Search (Top 5)', 'Brute Force Search (Top 5)'])
axs[1].set_title('Execution Time Distribution')
axs[1].set_ylabel('Time (seconds)')
axs[1].tick_params(axis='x', rotation=45)

fig.suptitle('Qdrant RAG Search Comparison (Top 5) - 1 Million Points', fontsize=14)
plt.tight_layout(rect=[0, 0.03, 1, 0.95])
plt.savefig("Qdrant_RAG_Search_Comparison_1M_Top5.png", dpi=300)
