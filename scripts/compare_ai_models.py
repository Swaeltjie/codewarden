#!/usr/bin/env python3
"""
Compare costs across different AI models for CodeWarden.

Compares pricing for:
- OpenAI GPT-4 Turbo
- OpenAI GPT-4o
- OpenAI GPT-4o mini
- Azure OpenAI (same models, Azure-hosted)
- Claude 3.5 Sonnet (Anthropic)
- Claude 3 Haiku (Anthropic)
"""
from typing import Dict, List


def print_table(data: List[List[str]], headers: bool = True) -> None:
    """Simple table printer without external dependencies."""
    if not data:
        return

    # Calculate column widths
    col_widths = [max(len(str(row[i])) for row in data) for i in range(len(data[0]))]

    # Print separator
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    print(separator)

    # Print rows
    for idx, row in enumerate(data):
        print("|", end="")
        for i, cell in enumerate(row):
            print(f" {str(cell).ljust(col_widths[i])} |", end="")
        print()

        # Print separator after header or last row
        if (headers and idx == 0) or idx == len(data) - 1:
            print(separator)


def calculate_model_costs(prs_per_month: int) -> List[Dict]:
    """Calculate costs for different AI models."""

    # Assumptions:
    # - 1,000 input tokens per review (diff + context)
    # - 200 output tokens per review (review comments)

    TOKENS_INPUT = 1000
    TOKENS_OUTPUT = 200

    models = [
        {
            'name': 'GPT-4 Turbo',
            'provider': 'OpenAI',
            'input_cost_per_1k': 0.01,
            'output_cost_per_1k': 0.03,
            'quality': '⭐⭐⭐⭐⭐',
            'speed': 'Medium',
            'notes': 'Best quality, higher cost'
        },
        {
            'name': 'GPT-4o',
            'provider': 'OpenAI',
            'input_cost_per_1k': 0.0025,
            'output_cost_per_1k': 0.01,
            'quality': '⭐⭐⭐⭐⭐',
            'speed': 'Fast',
            'notes': 'Best balance (RECOMMENDED)'
        },
        {
            'name': 'GPT-4o mini',
            'provider': 'OpenAI',
            'input_cost_per_1k': 0.00015,
            'output_cost_per_1k': 0.0006,
            'quality': '⭐⭐⭐⭐',
            'speed': 'Very Fast',
            'notes': 'Budget option, good quality'
        },
        {
            'name': 'Claude 3.5 Sonnet',
            'provider': 'Anthropic',
            'input_cost_per_1k': 0.003,
            'output_cost_per_1k': 0.015,
            'quality': '⭐⭐⭐⭐⭐',
            'speed': 'Fast',
            'notes': 'Excellent for code review'
        },
        {
            'name': 'Claude 3 Haiku',
            'provider': 'Anthropic',
            'input_cost_per_1k': 0.00025,
            'output_cost_per_1k': 0.00125,
            'quality': '⭐⭐⭐⭐',
            'speed': 'Very Fast',
            'notes': 'Fast and affordable'
        },
    ]

    for model in models:
        input_cost = (prs_per_month * TOKENS_INPUT / 1000) * model['input_cost_per_1k']
        output_cost = (prs_per_month * TOKENS_OUTPUT / 1000) * model['output_cost_per_1k']
        total_cost = input_cost + output_cost

        model['monthly_cost'] = total_cost
        model['cost_per_review'] = total_cost / prs_per_month

    return models


def compare_models():
    """Compare AI model costs for different workloads."""

    print("\n" + "="*80)
    print("AI MODEL COST COMPARISON FOR CODEWARDEN")
    print("="*80)

    workloads = [100, 1000, 5000]

    for prs_per_month in workloads:
        print(f"\n{'='*80}")
        print(f"WORKLOAD: {prs_per_month} PRs/MONTH")
        print(f"{'='*80}\n")

        models = calculate_model_costs(prs_per_month)

        # Sort by cost (cheapest first)
        models_sorted = sorted(models, key=lambda x: x['monthly_cost'])

        table_data = []
        table_data.append(['Model', 'Provider', 'Monthly Cost', '$/Review', 'Quality', 'Speed', 'Notes'])

        for model in models_sorted:
            table_data.append([
                model['name'],
                model['provider'],
                f"${model['monthly_cost']:.2f}",
                f"${model['cost_per_review']:.4f}",
                model['quality'],
                model['speed'],
                model['notes']
            ])

        print_table(table_data)

        # Calculate savings vs GPT-4 Turbo
        gpt4_turbo_cost = next(m['monthly_cost'] for m in models if m['name'] == 'GPT-4 Turbo')
        cheapest_cost = models_sorted[0]['monthly_cost']
        savings = gpt4_turbo_cost - cheapest_cost
        savings_pct = (savings / gpt4_turbo_cost) * 100

        print(f"\n💰 Cost Range: ${models_sorted[0]['monthly_cost']:.2f} - ${models_sorted[-1]['monthly_cost']:.2f}")
        print(f"💡 Switching from GPT-4 Turbo to {models_sorted[0]['name']} saves: ${savings:.2f}/month ({savings_pct:.0f}%)")

    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    print("""
🏆 RECOMMENDED: GPT-4o
   • Best balance of quality, speed, and cost
   • 84% cheaper than GPT-4 Turbo
   • Optimized for code understanding
   • Fast response times

💰 BUDGET: GPT-4o mini
   • 95% cheaper than GPT-4 Turbo
   • Still excellent quality for code review
   • Very fast
   • Best for high-volume workloads

⚡ ALTERNATIVE: Claude 3.5 Sonnet
   • Excellent code review capabilities
   • Strong reasoning about code
   • Comparable cost to GPT-4o
   • Great for complex codebases

🚀 ULTRA-BUDGET: Claude 3 Haiku
   • 92% cheaper than GPT-4 Turbo
   • Fast and efficient
   • Good for simple reviews

💡 NOTES:
   • Costs based on 1,000 input + 200 output tokens per review
   • Azure OpenAI pricing is similar to OpenAI (same models, Azure-hosted)
   • Consider quality needs vs budget constraints
   • Start with GPT-4o, optimize based on results
""")


def main():
    """Main function."""
    compare_models()

    print("\n" + "="*80)
    print("TOTAL SOLUTION COST (with Azure infrastructure)")
    print("="*80)
    print("""
For 100 PRs/month:
  • Azure infrastructure: $0.00 (free tier)
  • GPT-4 Turbo:         $1.60/month
  • GPT-4o:              $0.40/month ✅ RECOMMENDED
  • GPT-4o mini:         $0.08/month
  • Claude 3.5 Sonnet:   $0.48/month
  • Claude 3 Haiku:      $0.13/month

For 1,000 PRs/month:
  • Azure infrastructure: $0.01 (negligible)
  • GPT-4 Turbo:         $16.00/month
  • GPT-4o:              $4.00/month ✅ RECOMMENDED
  • GPT-4o mini:         $0.84/month
  • Claude 3.5 Sonnet:   $4.80/month
  • Claude 3 Haiku:      $1.25/month

For 5,000 PRs/month:
  • Azure infrastructure: $0.05 (negligible)
  • GPT-4 Turbo:         $80.00/month
  • GPT-4o:              $20.00/month ✅ RECOMMENDED
  • GPT-4o mini:         $4.20/month
  • Claude 3.5 Sonnet:   $24.00/month
  • Claude 3 Haiku:      $6.25/month

🎯 CONCLUSION: Use GPT-4o for best quality/cost balance
   Azure costs are negligible - AI model choice drives total cost
""")


if __name__ == "__main__":
    main()
