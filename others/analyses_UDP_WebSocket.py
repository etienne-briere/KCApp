import pandas as pd
import matplotlib.pyplot as plt
import glob

# Chemins vers les fichiers CSV
ws_files = glob.glob("data/ws_test*.csv")
udp_files = glob.glob("data/udp_test*.csv")

# bande passante maximale du réseau
bandwidth_max = 85000

def load_and_filter(files):
    dfs = []

    for file in files:
        df = pd.read_csv(file)
        
        # Calcul du temps écoulé depuis le début
        df["elapsed_time"] = df.iloc[:, 0] - df.iloc[0, 0]

        # Filtrage des valeurs extrêmes (1er et 99e percentiles)
        for col in ["Latence (ms)", "Bande passante (kbit/s)", "Taux de perte (%)"]:
            low, high = df[col].quantile([0.01, 0.99])
            df = df[(df[col] >= low) & (df[col] <= high)]

        dfs.append(df[["elapsed_time", "Latence (ms)", "Bande passante (kbit/s)", "Taux de perte (%)"]].reset_index(drop=True))
        
    # Couper toutes les séries à la même longueur
    min_length = min(len(df) for df in dfs)
    for i in range(len(dfs)):
        dfs[i] = dfs[i].iloc[:min_length]

    # Moyenne point par point
    merged = sum(dfs) / len(dfs)
    return merged

# Charger les données
ws_data = load_and_filter(ws_files)
udp_data = load_and_filter(udp_files)

# Fonction pour tracer chaque métrique
def plot_metric(metric, ylabel, title, mean=True, line=None, consommation=False, var=False, log_scale=False):
    plt.figure(figsize=(10, 4))
    
    if var :
        # Calcul de la variation du débit (écart-type)
        ws_std = ws_data[metric].std()
        udp_std = udp_data[metric].std()
        
        # Moyennes globales
        ws_mean = ws_data[metric].mean()
        udp_mean = udp_data[metric].mean()
        
        # Variation relative (en %)
        ws_var_rel = (ws_std / ws_mean) * 100 if ws_mean != 0 else 0
        udp_var_rel = (udp_std / udp_mean) * 100 if udp_mean != 0 else 0
        
        # ajout dans la légende du graphique
        # Tracé avec légendes enrichies
        plt.plot(ws_data["elapsed_time"], ws_data[metric],
                 label=f"WebSocket | σ = {ws_std:.2f} ({ws_var_rel:.1f}%)", color="blue", alpha=0.7)
        plt.plot(udp_data["elapsed_time"], udp_data[metric],
                 label=f"UDP | σ = {udp_std:.2f} ({udp_var_rel:.1f}%)", color="orange", alpha=0.7)
    
    if var == False :
        plt.plot(ws_data["elapsed_time"], ws_data[metric], label="WebSocket", color="blue", alpha=0.7)
        plt.plot(udp_data["elapsed_time"], udp_data[metric], label="UDP", color="orange", alpha=0.7)
        
    if mean :
        # Moyennes globales
        ws_mean = ws_data[metric].mean()
        udp_mean = udp_data[metric].mean()
        
        if not consommation :
            plt.axhline(ws_mean, linestyle="--", color="blue", label=f"Moy. WS : {ws_mean:.2f}")
            plt.axhline(udp_mean, linestyle="--", color="orange", label=f"Moy. UDP : {udp_mean:.2f}")
    
    if line :
        plt.axhline(line, linestyle="--", color="red", label=f"Bande passante disponible : {line} kbps")
        
    
    
    if consommation : 
        # Calcul de la consommation en %
        ws_data["conso_%"] = (ws_data["Bande passante (kbit/s)"] / bandwidth_max) * 100
        udp_data["conso_%"] = (udp_data["Bande passante (kbit/s)"] / bandwidth_max) * 100
        
        # Moyennes
        ws_mean_perc = ws_data["conso_%"].mean()
        udp_mean_perc = udp_data["conso_%"].mean()
        plt.axhline(ws_mean, linestyle=":", color="blue", label=f"Moy. Consommation de bande passante WS : {ws_mean_perc:.2f}%")
        plt.axhline(udp_mean, linestyle=":", color="orange", label=f"Moy. Consommation de bande passante UDP : {udp_mean_perc:.2f}%")
      
    if log_scale:
        plt.yscale("log")
        
    plt.xlabel("Temps écoulé (s)")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


# Tracer les trois métriques
plot_metric("Latence (ms)", "Latence (ms)", 
            "Comparaison de la latence entre UDP (orange) et WebSocket (bleu)"
            )
plot_metric("Bande passante (kbit/s)", "Débit (kbps)", 
            "Comparaison de la consommation de bande passante entre UDP (orange) et WebSocket (bleu)", 
            line = bandwidth_max, 
            consommation= True,
            log_scale = True
            )
plot_metric("Bande passante (kbit/s)", "Débit (kbps)", 
            "Comparaison du débit moyen entre UDP (orange) et WebSocket (bleu)",
            var = True,
            log_scale = True
            )
plot_metric("Taux de perte (%)", "Taux de perte (%)", 
            "Comparaison du taux de perte entre UDP (orange) et WebSocket (bleu)", 
            mean = False
            )



# =============================================================================
# def plot_bandwidth_usage(data_ws, data_udp):
#     # Calcul de la consommation en %
#     ws_data["conso_%"] = (ws_data["Bande passante (kbit/s)"] / bandwidth_max) * 100
#     udp_data["conso_%"] = (udp_data["Bande passante (kbit/s)"] / bandwidth_max) * 100
# 
#     plt.figure(figsize=(10, 4))
#     plt.plot(ws_data["elapsed_time"], ws_data["conso_%"], label="WebSocket", color="blue", alpha=0.7)
#     plt.plot(udp_data["elapsed_time"], udp_data["conso_%"], label="UDP", color="orange", alpha=0.7)
# 
#     # Moyennes
#     ws_mean = ws_data["conso_%"].mean()
#     udp_mean = udp_data["conso_%"].mean()
#     plt.axhline(ws_mean, linestyle="--", color="blue", label=f"Moy. WS : {ws_mean:.2f}%")
#     plt.axhline(udp_mean, linestyle="--", color="orange", label=f"Moy. UDP : {udp_mean:.2f}%")
# 
#     plt.xlabel("Temps écoulé (s)")
#     plt.ylabel("Consommation de la bande passante (%)")
#     plt.title("Consommation de la bande passante dans le temps")
#     plt.legend()
#     plt.grid(True)
#     plt.tight_layout()
#     plt.show()
# 
# plot_bandwidth_usage(ws_data, udp_data)
# 
# # Calcul de la variation du débit (écart-type)
# ws_variation_debit = ws_data["Bande passante (kbit/s)"].std()
# udp_variation_debit = udp_data["Bande passante (kbit/s)"].std()
# 
# print(f"Variation du débit WebSocket (écart-type) : {ws_variation_debit:.2f} kbps")
# print(f"Variation du débit UDP (écart-type) : {udp_variation_debit:.2f} kbps")
# 
# =============================================================================



