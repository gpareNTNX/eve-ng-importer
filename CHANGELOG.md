# Changelog

## 0.2.0 — Smart Import

- Détection automatique constructeur / produit / version.
- Matching des profils avec les templates réellement installés dans EVE-NG.
- Score de confiance et explication de la recommandation.
- Import QEMU multi-disques.
- Préservation des noms de disques EVE déjà valides dans une archive.
- Apprentissage du layout disque depuis les images existantes du même template.
- Détection du dossier cible et inventaire des versions déjà présentes.
- Disques additionnels générés par profil, notamment vManage `virtiob.qcow2` 100 Go.
- Import QEMU préparé dans un dossier de staging avant activation.
- Endpoint `/api/installed`.
- Nouvelle interface Smart Import avec plan visuel des disques.
- Mode manuel 0.1 conservé comme fallback.
- Profils étendus Cisco, Fortinet, Palo Alto, Juniper, F5, Aruba, Arista, VMware, Linux, Windows, Nutanix et autres.
- Suite de tests étendue pour détection, multi-disques, conflits et sécurité d'archive.

## 0.1.0

- Upload chunked.
- Extraction sécurisée ZIP/TAR/GZ.
- QEMU/ISO/IOL/Dynamips.
- Conversion qemu-img.
- Découverte des templates EVE-NG.
- Dry-run, backups et fixpermissions.
