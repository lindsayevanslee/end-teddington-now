#!/usr/bin/env python3
"""
Find comedian-footballer combinations with combined probability of 0.000001 (rounded).

On the podcast from 2025-11-25, Max checked the website and said the correct answer was showing a probability of 0.0001%. This script finds all combinations of comedians and footballers who had a combined probability of 0.000001 on that day when they were looking at the data. These subsets will then be used to filter the lists of comedians and footballers shown on the website moving forward.

This script:
1. Loads probability data from a snapshot folder
2. Calculates all comedian × footballer combinations
3. Finds combinations where the product equals 0.000001 when rounded to 6 decimal places
4. Saves the results to CSV files
"""

import pandas as pd
import argparse
from pathlib import Path

def find_combinations_with_target_probability(snapshot_folder, target_prob=0.000001):
    """
    Find all comedian-footballer combinations with combined probability equal to target_prob when rounded.
    
    Args:
        snapshot_folder: Path to folder containing comedians_probability.csv and footballers_probability.csv
        target_prob: Target probability (default 0.000001)
    
    Returns:
        DataFrame with matching combinations
    """
    snapshot_path = Path(snapshot_folder)
    
    # Load probability data
    comedians_file = snapshot_path / 'comedians_probability.csv'
    footballers_file = snapshot_path / 'footballers_probability.csv'
    
    if not comedians_file.exists():
        raise FileNotFoundError(f"Comedians file not found: {comedians_file}")
    if not footballers_file.exists():
        raise FileNotFoundError(f"Footballers file not found: {footballers_file}")
    
    print(f"Loading data from {snapshot_path}...")
    comedians_df = pd.read_csv(comedians_file)
    footballers_df = pd.read_csv(footballers_file)
    
    print(f"Loaded {len(comedians_df)} comedians and {len(footballers_df)} footballers")
    
    # Create all combinations using merge (cartesian product)
    # Add a dummy key to create all combinations
    comedians_renamed = comedians_df[['Name', 'Probability']].rename(
        columns={'Name': 'Comedian', 'Probability': 'Comedian_Probability'}
    )
    comedians_renamed['key'] = 1
    
    footballers_renamed = footballers_df[['Name', 'Probability']].rename(
        columns={'Name': 'Footballer', 'Probability': 'Footballer_Probability'}
    )
    footballers_renamed['key'] = 1
    
    combinations = pd.merge(
        comedians_renamed,
        footballers_renamed,
        on='key'
    ).drop('key', axis=1)
    
    # Calculate combined probability
    combinations['Combined_Probability'] = (
        combinations['Comedian_Probability'] * combinations['Footballer_Probability']
    )
    
    # Round to 6 decimal places
    combinations['Rounded_Probability'] = combinations['Combined_Probability'].round(6)
    
    # Filter for target probability (exact match)
    matching = combinations[combinations['Rounded_Probability'] == target_prob].copy()
    
    # Sort by combined probability (descending) for easier reading
    matching = matching.sort_values('Combined_Probability', ascending=False)
    
    return matching

def main():
    parser = argparse.ArgumentParser(
        description='Find comedian-footballer combinations with probability of 0.000001 (rounded)'
    )
    parser.add_argument(
        'snapshot_folder',
        type=str,
        nargs='?',
        default='data/snapshots/wdydy_2025-11-25',
        help='Path to snapshot folder containing probability CSVs (default: data/snapshots/wdydy_2025-11-25)'
    )
    parser.add_argument(
        '--target',
        type=float,
        default=0.000001,
        help='Target probability (default: 0.000001)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output CSV file path (optional)'
    )
    
    args = parser.parse_args()
    
    try:
        matching_combinations = find_combinations_with_target_probability(
            args.snapshot_folder,
            target_prob=args.target
        )
        
        print(f"\n{'='*80}")
        print(f"Found {len(matching_combinations)} combinations with rounded probability = {args.target}")
        print(f"{'='*80}\n")
        
        # Define output file paths
        comedians_output_file = 'data/comedians_subset_2025-11-25.csv'
        footballers_output_file = 'data/footballers_subset_2025-11-25.csv'
        
        if len(matching_combinations) > 0:
            # Display first 10 results
            print("First 10 matching combinations:")
            print(matching_combinations.head(10).to_string(index=False))
            if len(matching_combinations) > 10:
                print(f"\n... and {len(matching_combinations) - 10} more combinations (use --output to save all results)")
            
            # Extract unique comedians and footballers
            unique_comedians = matching_combinations['Comedian'].unique()
            unique_footballers = matching_combinations['Footballer'].unique()
            
            # Save to CSV if output path specified
            if args.output:
                matching_combinations.to_csv(args.output, index=False)
                print(f"\nAll {len(matching_combinations)} combinations saved to: {args.output}")
        else:
            print("No matching combinations found.")
            unique_comedians = []
            unique_footballers = []
        
        # Create DataFrames and save to CSV files (common logic)
        comedians_subset_df = pd.DataFrame({'Name': sorted(unique_comedians)})
        footballers_subset_df = pd.DataFrame({'Name': sorted(unique_footballers)})
        
        comedians_subset_df.to_csv(comedians_output_file, index=False)
        footballers_subset_df.to_csv(footballers_output_file, index=False)
        
        if len(unique_comedians) > 0:
            print(f"\nUnique comedians ({len(unique_comedians)}) saved to: {comedians_output_file}")
            print(f"Unique footballers ({len(unique_footballers)}) saved to: {footballers_output_file}")
        else:
            print(f"\nEmpty CSV files created: {comedians_output_file}, {footballers_output_file}")
        
        # Print summary statistics
        print(f"\n{'='*80}")
        print("Summary Statistics:")
        print(f"{'='*80}")
        if len(matching_combinations) > 0:
            print(f"Total matching combinations: {len(matching_combinations)}")
            print(f"Min combined probability: {matching_combinations['Combined_Probability'].min():.9f}")
            print(f"Max combined probability: {matching_combinations['Combined_Probability'].max():.9f}")
            print(f"Mean combined probability: {matching_combinations['Combined_Probability'].mean():.9f}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())

