import pandas as pd
import numpy as np

class TeddingtonSightingModel:
    def __init__(self, comedians_df, footballers_df, 
                 combinations_file='data/combinations_2025-11-25.csv'):
        self.comedians = comedians_df.copy()
        self.footballers = footballers_df.copy()
        
        # Load combinations file and extract unique (Name, URL) pairs for comedians and footballers
        try:
            combinations_df = pd.read_csv(combinations_file)
            # Create sets of (Name, URL) tuples for precise matching
            # Handle NaN values by converting to empty string for consistency
            comedian_urls = combinations_df['Comedian_URL'].fillna('')
            footballer_urls = combinations_df['Footballer_URL'].fillna('')
            self.comedians_subset = set(zip(combinations_df['Comedian'], comedian_urls))
            self.footballers_subset = set(zip(combinations_df['Footballer'], footballer_urls))
            print(f"Loaded {len(self.comedians_subset)} unique (Name, URL) comedian pairs from combinations file")
            print(f"Loaded {len(self.footballers_subset)} unique (Name, URL) footballer pairs from combinations file")
        except FileNotFoundError:
            print(f"Warning: {combinations_file} not found. All comedians and footballers will be included.")
            self.comedians_subset = None
            self.footballers_subset = None
        
    def calculate_comedian_probability(self, row):
        """Calculate probability for a comedian being in Teddington"""
        
        # Check if comedian (Name, URL) pair is in subset (if subset is defined)
        if self.comedians_subset is not None:
            comedian_name = row['Name']
            comedian_url = row.get('URL', '')
            # Handle NaN values by converting to empty string
            if pd.isna(comedian_url):
                comedian_url = ''
            if (comedian_name, comedian_url) not in self.comedians_subset:
                return 0.0
        
        # Dead people don't visit Teddington
        if pd.notna(row['DeathYear']):
            return 0.0
        
        # Female comedians have probability of 0
        if pd.notna(row.get('Gender')) and str(row['Gender']).strip().lower() == 'female':
            return 0.0
        
        # Initialize base probability
        probability = 1.0
        
        # 1. Distance Component (most important - 50% weight)
        distance_score = 0.1  # default for unknown location
        if pd.notna(row['DistanceFromTeddington']):
            distance_km = row['DistanceFromTeddington']
            if distance_km <= 3:  # Walking distance
                distance_score = 1.0
            elif distance_km <= 10:  # Very local
                distance_score = 0.8
            elif distance_km <= 20:  # Greater London
                distance_score = 0.4
            elif distance_km <= 50:  # Commutable
                distance_score = 0.2
            else:
                distance_score = 0.05
        
        # 2. Age/Mobility Component (20% weight)
        age_score = 0.5  # default
        if pd.notna(row['Age']):
            age = row['Age']
            if 30 <= age <= 60:  # Peak mobility years
                age_score = 1.0
            elif 25 <= age <= 70:
                age_score = 0.7
            elif age < 25 or age > 70:
                age_score = 0.4
        
        # 3. Fame/Activity Component using PageLength (20% weight)
        fame_score = 0.3  # default
        if pd.notna(row['PageLength']):
            # Log scale for page length
            if row['PageLength'] > 10000:  # Very famous
                fame_score = 0.1
            elif row['PageLength'] > 5000:  # Well known
                fame_score = 0.3
            elif row['PageLength'] > 2000:  # Known
                fame_score = 0.9
            else:
                fame_score = 0.3
        
        # 4. Local connection bonus (10% weight)
        local_bonus = 0.0
        if pd.notna(row['Birthplace']):
            birthplace = str(row['Birthplace']).lower()
            if any(place in birthplace for place in 
                   ['richmond', 'twickenham', 'teddington', 'kingston', 'hampton']):
                local_bonus = 1.0  # Very strong local connection
            elif 'london' in birthplace:
                local_bonus = 0.3
        
        # Weighted combination
        probability = (
            0.50 * distance_score +
            0.20 * age_score +
            0.20 * fame_score +
            0.10 * local_bonus
        )
        
        return probability
    
    def calculate_footballer_probability(self, row):
        """Calculate probability for a footballer being in Teddington"""
        
        # Check if footballer (Name, URL) pair is in subset (if subset is defined)
        if self.footballers_subset is not None:
            footballer_name = row['Name']
            footballer_url = row.get('URL', '')
            # Handle NaN values by converting to empty string
            if pd.isna(footballer_url):
                footballer_url = ''
            if (footballer_name, footballer_url) not in self.footballers_subset:
                return 0.0
        
        # 1. Active Status Filter
        # Priority: Recently retired > Long retired > Active
        base_multiplier = 1.0
        is_active = row.get('IsActive') == 'Yes'
        
        if is_active:
            # Currently active players are least likely
            base_multiplier = 0.3
        else:
            # Try to get YearEnded, or estimate it if missing
            year_ended = None
            if pd.notna(row.get('YearEnded')):
                try:
                    year_ended = int(row['YearEnded'])
                except (ValueError, TypeError):
                    year_ended = None
            
            # If YearEnded is missing, estimate it as YearStarted + 10 (average career length)
            if year_ended is None:
                if pd.notna(row.get('YearStarted')):
                    try:
                        year_started = int(row['YearStarted'])
                        year_ended = year_started + 10  # Average career length
                        # Ensure it's not in the future
                        if year_ended > 2024:
                            year_ended = 2024
                    except (ValueError, TypeError):
                        # Can't determine retirement status, treat as long retired
                        base_multiplier = 0.6
                else:
                    # Can't determine retirement status, treat as long retired
                    base_multiplier = 0.6
            
            # Calculate years since retirement if we have a valid year_ended
            if year_ended is not None:
                years_since_retirement = 2024 - year_ended
                if years_since_retirement <= 0:
                    # Still active or just retired this year
                    base_multiplier = 0.3
                elif years_since_retirement <= 10:
                    # Recently retired (most likely)
                    base_multiplier = 1.0
                else:
                    # Long retired (less likely than recently retired, but more likely than active)
                    base_multiplier = 0.6
        
        # 2. Distance Component (40% weight)
        distance_score = 0.05  # default for unknown
        if pd.notna(row['Scraped_DistanceFromTeddington']):
            distance_km = row['Scraped_DistanceFromTeddington']
            if distance_km <= 5:  # Very local
                distance_score = 1.0
            elif distance_km <= 15:  # Local area
                distance_score = 0.7
            elif distance_km <= 30:  # Greater London
                distance_score = 0.4
            elif distance_km <= 60:  # Commutable
                distance_score = 0.2
            else:
                distance_score = 0.02
        
        # 3. Club Connection (30% weight)
        # SW London clubs are very close to Teddington
        southwest_clubs = ['chelsea', 'fulham', 'brentford', 'qpr', 'wimbledon']
        london_clubs = ['tottenham', 'arsenal', 'west ham', 'charlton', 
                       'crystal palace', 'millwall', 'leyton orient']
        
        club_score = 0.1  # default
        if pd.notna(row['SquadHistory']):
            squad_history = str(row['SquadHistory']).lower()
            if any(club in squad_history for club in southwest_clubs):
                club_score = 1.0  # Very strong connection
            elif any(club in squad_history for club in london_clubs):
                club_score = 0.5  # London connection
            else:
                club_score = 0.1
        
        # 4. Age Factor (20% weight)
        age_score = 0.5  # default
        if pd.notna(row['Scraped_Age']):
            age = row['Scraped_Age']
            if 25 <= age <= 40:  # Peak playing/active age
                age_score = 1.0
            elif 40 < age <= 55:  # Recently retired, still mobile
                age_score = 0.7
            elif age < 25:  # Young player
                age_score = 0.6
            else:
                age_score = 0.3
        
        # 5. Career Prominence (10% weight)
        prominence_score = 0.3  # default
        if pd.notna(row['YearStarted']):
            try:
                year_started = int(row['YearStarted'])
                
                # Handle YearEnded - estimate as YearStarted + 10 if missing
                year_ended = None
                if pd.notna(row.get('YearEnded')):
                    try:
                        year_ended = int(row['YearEnded'])
                    except (ValueError, TypeError):
                        year_ended = None
                
                # If YearEnded is missing, estimate it as YearStarted + 10 (average career length)
                if year_ended is None:
                    year_ended = year_started + 10
                    # Ensure it's not in the future
                    if year_ended > 2024:
                        year_ended = 2024
                
                career_length = year_ended - year_started
                if career_length >= 15:  # Long career
                    prominence_score = 0.9
                elif career_length >= 10:
                    prominence_score = 0.7
                elif career_length >= 5:
                    prominence_score = 0.5
                else:
                    prominence_score = 0.3
            except (ValueError, TypeError):
                # If YearStarted can't be converted, use default
                prominence_score = 0.3
        
        # Weighted combination with base multiplier
        probability = base_multiplier * (
            0.40 * distance_score +
            0.30 * club_score +
            0.20 * age_score +
            0.10 * prominence_score
        )
        
        return probability
    
    def generate_probability_csvs(self, comedians_output='data/comedians_probability.csv', 
                                 footballers_output='data/footballers_probability.csv'):
        """Generate probability CSVs for both comedians and footballers"""
        
        # Calculate comedian probabilities
        self.comedians['raw_probability'] = self.comedians.apply(
            self.calculate_comedian_probability, axis=1
        )
        
        # Normalize to sum to 1
        total_comedian_prob = self.comedians['raw_probability'].sum()
        if total_comedian_prob > 0:
            self.comedians['Probability'] = self.comedians['raw_probability'] / total_comedian_prob
        else:
            self.comedians['Probability'] = 0
        
        # Create comedian output
        comedians_output_df = self.comedians[['Name', 'URL', 'Probability']].copy()
        comedians_output_df = comedians_output_df.sort_values('Probability', ascending=False)
        comedians_output_df.to_csv(comedians_output, index=False)
        
        # Calculate footballer probabilities
        self.footballers['raw_probability'] = self.footballers.apply(
            self.calculate_footballer_probability, axis=1
        )
        
        # Normalize to sum to 1
        total_footballer_prob = self.footballers['raw_probability'].sum()
        if total_footballer_prob > 0:
            self.footballers['Probability'] = self.footballers['raw_probability'] / total_footballer_prob
        else:
            self.footballers['Probability'] = 0
        
        # Create footballer output
        footballers_output_df = self.footballers[['Name', 'URL', 'Probability']].copy()
        footballers_output_df = footballers_output_df.sort_values('Probability', ascending=False)
        footballers_output_df.to_csv(footballers_output, index=False)
        
        # Print summary statistics
        print("=" * 50)
        print("COMEDIAN PROBABILITIES")
        print("=" * 50)
        print(f"Total comedians: {len(comedians_output_df)}")
        print(f"Comedians with P > 0: {(comedians_output_df['Probability'] > 0).sum()}")
        print("\nTop 10 Most Likely Comedians:")
        print(comedians_output_df.head(10).to_string(index=False))
        
        print("\n" + "=" * 50)
        print("FOOTBALLER PROBABILITIES")
        print("=" * 50)
        print(f"Total footballers: {len(footballers_output_df)}")
        print(f"Footballers with P > 0: {(footballers_output_df['Probability'] > 0).sum()}")
        print("\nTop 10 Most Likely Footballers:")
        print(footballers_output_df.head(10).to_string(index=False))
        
        return comedians_output_df, footballers_output_df

# Usage:
# Load your data
comedians_df = pd.read_csv('data/comedians_enriched.csv')
footballers_df = pd.read_csv('data/footballers_enriched.csv')

# Create model and generate CSVs
model = TeddingtonSightingModel(comedians_df, footballers_df)
comedians_probs, footballers_probs = model.generate_probability_csvs()

# The files 'comedians_probability.csv' and 'footballers_probability.csv' 
# will be created with just Name and Probability columns