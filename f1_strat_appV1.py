import streamlit as st
import fastf1
import pandas as pd
import numpy as np
import os
os.makedirs("cache_dir", exist_ok=True)
fastf1.Cache.enable_cache('cache_dir')
from sklearn.linear_model import LinearRegression
from itertools import product, combinations
import matplotlib.pyplot as plt


def main():
    st.title("F1 Strategy Predictor")
    bestlap = get_laptime()
    if bestlap is None:
        return
    
    nlaps = get_nlaps()
    if nlaps is None:
        return
    
    fuel =get_fuel(nlaps)
    if fuel is None:
         return
    
    session = get_datarace()
    if session is None:
         return
    
    lap_time_evolution = get_lap_time_evolution(session)

    pit_loss = get_pitloss()
    if pit_loss is None:
         return
    
    strategy = get_strat(nlaps, bestlap, lap_time_evolution, pit_loss)

    results(strategy, nlaps,)


# Convert laptime to seconds.
def convert_laptime(laptime):
    minutes, seconds_and_milliseconds = laptime.split(":")
    seconds, milliseconds = seconds_and_milliseconds.split(".")
    return int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


#get the laptime in seconds for each compound.
def get_laptime():
     bestlapsoft = st.text_input("Insert the best lap time in minutes, seconds and milliseconds (mm:ss.sss) for the soft tyre compound: ", key="bestlapsoft").strip()
     bestlapmedium = st.text_input("Insert the best lap time in minutes, seconds and milliseconds (mm:ss.sss) for the medium tyre compound: ", key="bestlapmedium").strip()
     bestlaphard = st.text_input("Insert the best lap time in minutes, seconds and milliseconds (mm:ss.sss) for the hard tyre compound: ", key="bestlaphard").strip()

     if bestlapsoft == "" or bestlapmedium == "" or bestlaphard == "":
          return None

     try:
          return {"soft": convert_laptime(bestlapsoft),"medium":convert_laptime(bestlapmedium),"hard":convert_laptime(bestlaphard)}
     except ValueError:
          st.warning("Invalid input, please insert the lap time in the requested format e.g '1:23.500' ")
          return None
     

               
          
#Convert number of laps to integer.
def convert_nlaps(nlaps):
    if nlaps.isnumeric():
        return int(nlaps)
    raise ValueError


#Get the number of laps of the race.
def get_nlaps():
    nlaps = st.text_input(
        "Insert the race's number of laps:",
        key="numberoflaps"
    ).strip()

    if nlaps == "":
        return None

    try:
        return convert_nlaps(nlaps)
    except ValueError:
        st.error("Your input should be a number, please insert a valid number of laps (e.g. '54')")
        return None

#Get the total fuel needed for the completion of the race, with precision dowwn to the milliliter.
def get_fuel(nlaps):

     fuel_per_lap = (st.text_input("Insert fuel consumption per lap in liters, with 3 decimal places: ", key = "fuelplap").strip())
     if fuel_per_lap == "":
          return None    
     try:
          fuel_per_lap = float(fuel_per_lap)
          fuel = int(nlaps) * fuel_per_lap
          fuel = round(fuel, 3)
          st.write(f"You will need {fuel} litters of fuel for the race")
          
         
     except ValueError:
          st.error("Invalid input, please insert a number with 3 decimal places (e.g. 2.300)")
          return None
     return fuel

#Getting the race session from which the fastf1 library will be used to gather data to make the models prediction.
def get_datarace():
        
     year = (st.text_input("Enter the year of the race in which you want to base the predictions of the model: ", key="raceyear").strip())
     if year == "":
          return None
     year = int(year)
     calendar = fastf1.get_event_schedule(year) #Get the calendat for the year inputed.
     #Simplify the data to make it easier to compare with user input.
     event_names = calendar['EventName'].str.lower().values
     locations = calendar['Location'].str.lower().values
     countries = calendar['Country'].str.lower().values
     circuit = st.text_input("Enter the circuit/country/location of the race in which you want to base the predictions of the model: ", key="circuit").strip().lower()
      
     if circuit == "":
          return None
     #Veryfying if the user input is valid, and, if not, ask for it again.
     if year < 2018:
          st.error("Invalid year. Data for model is only available from 2018 onward, assure also that you have inputed an integer.")
          return None
            

     elif circuit not in event_names and circuit not in locations and circuit not in countries:
          st.error("Invalid circuit. Please enter a valid circuit name from the F1 calendar of the selected year.")
          return None
            
     session = fastf1.get_session(year,circuit,"R")
     return session

# Gettig the data to model numerically the evolution of laptime throuout the race.
def get_lap_time_evolution(session):

    session.load(laps=True, telemetry=False, weather=False, messages=False)
    laps = session.laps.pick_quicklaps()
    #Eliminate the laps in which there is missing info.
    clean_laps = laps.dropna(subset = ['TyreLife' , 'Compound' , 'LapTime']).copy()
    #Convert each lap time to seconds.
    clean_laps["LapTimeinSeconds"] = clean_laps["LapTime"].dt.total_seconds()
    #Create a dict to store results.
    lap_time_evolution = {}

    for compound in clean_laps["Compound"].unique():
        compound_laps = clean_laps[clean_laps["Compound"] == compound]

        #Verify if the sample size is big enough to make a prediction
        if len(compound_laps) < 5:
            continue

        x = compound_laps[["TyreLife", "LapNumber"]].values #Variable x includes both factors which can impact lap time, tyre degradation by "TyreLife" and other effects like fuel consumption, track evolution and traffic by "LapNumber". 
        y = compound_laps["LapTimeinSeconds"].values
        model = LinearRegression()
        model.fit(x, y)
        #Store for each compund it's degradation results and fuel usage time variation, to obtain a more accurate prediction.
        lap_time_evolution[compound.lower()] = {"tyre_loss": model.coef_[0], "fuel_effect": model.coef_[1]}

    return lap_time_evolution

# Calculation of the best possible strategy of the race
def get_strat( nlaps, baselap, lap_time_evolution, pit_loss):

     # List to store all possible strategies.
     strategies=[]
     # Create a list composed of all compunds.
     compounds = list(lap_time_evolution.keys())

     # Try every number of plausible stops in an f1 race, recurring that this model expects normal racing conditions in the current version, SC, VSC and traffic are not being taken account.
     for n_pitstops in range(1,4):
          # Try every combination possible of the dry weather, tyre compounds while making 4 pitstops.
          for tyre_sequence in product(compounds, repeat = n_pitstops + 1):
               #Assuring that we use at least two different tyre compounds.
               if len(set(tyre_sequence)) < 2:
                    continue

               #All possible laps in which to pit.
               combinations(range(1,nlaps) , n_pitstops)
               #Pick the laps in which to pit
               for pit_laps  in combinations(range(1,nlaps) , n_pitstops):
                    # Create the variable total time which stores the total time of the race.
                    total_time=0
                    lap_times=[]

                    for lap in range(1, nlaps + 1):
                         stint = sum (lap > pit_lap for pit_lap in pit_laps) #Finding the current stint.
                         tyre = tyre_sequence[stint] #Finding the tyre currently in use.
                         #Calculation of the tyres age
                         if stint == 0:
                              tyre_age = int(lap)

                         else:
                              tyre_age = int(lap) - int(pit_laps[stint - 1])

                         tyre_data = lap_time_evolution[tyre]
                         lap_time = (baselap[tyre] + tyre_data["tyre_loss"] * (tyre_age - 1) + tyre_data["fuel_effect"] * (lap - 1))
                         lap_time = round(lap_time, 3)
                         lap_times.append(lap_time)
                         total_time += lap_time
                         if lap in pit_laps:
                              total_time += pit_loss

                    strategies.append({"pit stops":n_pitstops,"pit laps":pit_laps,"tyres":tyre_sequence,"total time":total_time,"lap times":lap_times})
     best_strategy = min(strategies, key=lambda strategy: strategy["total time"])
     return best_strategy

#Determinating how uch is lost ate each pitstop
def convert_pitloss(pitloss):
     return float(pitloss)


def get_pitloss():
          pit_loss = st.text_input("Insert, in seconds, the estimated time loss for each pit stop relative to the normal lap: ", key = "pitloss").strip()

          if pit_loss == "":
               return None
          
          try:
               return convert_pitloss(pit_loss)
          
          except ValueError:
               st.error("Please insert a valid number.")
               return None

#Printing the results.
def results(strategy,nlaps,):
     st.write("The best strategy is:")
     st.write(f"Number of pit stops: {strategy['pit stops']}")
     st.write(f"Pit laps: {', '.join(map(str, strategy['pit laps']))}")
     st.write(f"Tyres: {' -> '.join(strategy['tyres'])}")
     total_min = int(strategy["total time"] / 60)
     total_sec = strategy["total time"] - total_min * 60
     st.write(f"Total race time: {total_min} minutes and {total_sec:.3f} seconds")
     laps=[]
     for lap in range(1,nlaps+1):
            laps.append(lap)
     datagraph = pd.DataFrame({"Lap":laps,"Lap time (s)":strategy["lap times"]})
     datagraph.set_index("Lap", inplace=True)
     st.subheader("Lap time evolution:")
     st.line_chart(datagraph, x_label = "Lap", y_label = "Lap time (s)")
     
     
     
     
if __name__ == "__main__":
     main()