// Extrait à reprendre dans le build.gradle.kts de votre module applicatif.
// Rien d'exotique : une dépendance, et les briques de coroutines et de cycle
// de vie que la plupart des applications ont déjà.

android {
    // Kadb cible Android à partir de l'API 23. Si votre minSdk est plus bas,
    // c'est le seul point bloquant du dossier.
    defaultConfig {
        minSdk = 23
    }
}

dependencies {
    // Client ADB en Kotlin : parle directement au démon du casque, sans
    // binaire adb ni serveur ADB.
    // https://central.sonatype.com/artifact/com.flyfishxu/kadb
    implementation("com.flyfishxu:kadb:2.1.3")

    // Découverte des casques par mDNS. Facultatif : utile seulement si vous
    // voulez éviter de saisir l'adresse IP à la main.
    // implementation("com.flyfishxu:kadb-mdns:2.1.3")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.4")
}
