package fr.univrennes2.apex.casque

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle

/**
 * Écran d'exemple : à reprendre tel quel, ou à découper.
 *
 * Il n'a rien d'obligatoire — toute la logique vit dans [CasqueViewModel] et
 * [CasqueQuest]. Il sert de référence sur deux points d'ergonomie qui ne se
 * devinent pas :
 *
 * **Un bouton principal, très grand.** Dans quatre-vingt-dix pour cent des
 * cas, l'investigateur veut « préparer la séance » et rien d'autre. Les
 * commandes séparées existent pour les incidents, pas pour l'usage courant.
 *
 * **Un journal visible en permanence.** Le pilotage agit sur un appareil qui
 * n'est pas sous les yeux : sans retour écrit, on ne sait pas si le jeu a
 * démarré. C'est ce qui distingue un outil utilisable en chambre d'une
 * télécommande dont on doute à chaque appui.
 */
@Composable
fun EcranCasque(
    modele: CasqueViewModel,
    modifier: Modifier = Modifier,
) {
    val etat by modele.etat.collectAsStateWithLifecycle()
    var adresse by remember { mutableStateOf(etat.adresse) }

    Column(
        modifier = modifier.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Casque APEX", style = MaterialTheme.typography.titleLarge)

        // -- adresse ---------------------------------------------------------
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = adresse,
                onValueChange = { adresse = it; modele.adresse = it },
                label = { Text("Adresse IP du casque") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            OutlinedButton(
                onClick = { modele.rafraichirEtat() },
                enabled = !etat.occupe,
            ) { Text("État") }
        }

        // -- état ------------------------------------------------------------
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                LigneEtat("Connexion", if (etat.connecte) etat.modele.ifBlank { "connecté" } else "absent")
                LigneEtat("Batterie", etat.batterie?.let { "$it %" } ?: "—")
                LigneEtat("Application", etat.application.ifBlank { "—" })
                LigneEtat(
                    "Limite de jeu",
                    when (etat.limiteActive) {
                        true -> "active"
                        false -> "désactivée"
                        null -> "—"
                    },
                )
            }
        }

        // -- action principale ------------------------------------------------
        Button(
            onClick = { modele.preparerSeance() },
            enabled = !etat.occupe,
            modifier = Modifier.fillMaxWidth().heightIn(min = 72.dp),
        ) { Text("Préparer la séance", fontSize = 18.sp, fontWeight = FontWeight.SemiBold) }

        Text(
            "Réveille le casque, neutralise le capteur de proximité et la veille, " +
                "désactive la limite de jeu, puis lance le jeu. Casque posé sur la table.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        // -- commandes séparées ------------------------------------------------
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                BoutonLarge("Désactiver la limite de jeu", etat.occupe) { modele.desactiverLimite() }
                BoutonLarge("Rétablir la limite de jeu", etat.occupe) { modele.activerLimite() }
                BoutonLarge("Lancer le jeu seulement", etat.occupe) { modele.lancerJeu() }
                BoutonLarge("Arrêter le jeu", etat.occupe, danger = true) { modele.arreterJeu() }
                BoutonLarge("Retrouver l'identifiant du jeu", etat.occupe) { modele.chercherLeJeu() }
            }
        }

        // -- journal ------------------------------------------------------------
        Card(modifier = Modifier.fillMaxWidth().weight(1f)) {
            LazyColumn(Modifier.padding(12.dp)) {
                items(etat.journal) { ligne ->
                    Text(
                        "${ligne.heure}  ${ligne.texte}",
                        fontSize = 13.sp,
                        color = if (ligne.erreur) Color(0xFFB91C1C)
                        else MaterialTheme.colorScheme.onSurface,
                    )
                }
            }
        }
    }
}

@Composable
private fun LigneEtat(libelle: String, valeur: String) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(libelle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 14.sp)
        Text(valeur, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
    }
}

@Composable
private fun BoutonLarge(
    libelle: String,
    occupe: Boolean,
    danger: Boolean = false,
    action: () -> Unit,
) {
    OutlinedButton(
        onClick = action,
        enabled = !occupe,
        // Cibles larges : la commande se donne debout, au pied du lit, parfois
        // avec des gants.
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
        colors = if (danger) {
            ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFB91C1C))
        } else {
            ButtonDefaults.outlinedButtonColors()
        },
    ) { Text(libelle) }
}
