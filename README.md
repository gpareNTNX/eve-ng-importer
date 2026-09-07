# EVE Image Forge 0.1.0

Application web locale pour préparer des images EVE-NG sans manipuler manuellement les dossiers, conversions et permissions.

## Formats

- QEMU directs: `.qcow2`, `.qcow`, `.vmdk`, `.vdi`, `.raw`, `.img`
- Installation ISO: `.iso` + création d'un disque QCOW2 vierge
- Cisco IOL: `.bin`
- Dynamips: `.image`
- Archives: `.zip`, `.tgz`, `.tar.gz`, `.tar`, `.ova`, `.gz` (l'application cherche les images supportées à l'intérieur)

## Installation

Copier le dossier `eve-image-forge` sur le serveur EVE-NG puis:

```bash
cd eve-image-forge
sudo ./install.sh
```

Le script affiche l'URL (port `8088`) et un jeton d'accès. Ouvrir l'URL depuis un navigateur, entrer le jeton, puis glisser-déposer une image.

## Ce que fait l'application

1. Upload par morceaux de 8 MiB, adapté aux gros fichiers.
2. Extraction sécurisée des archives (blocage des chemins `../`, liens symboliques et devices).
3. Détection de QEMU / ISO / IOL / Dynamips.
4. Découverte des templates QEMU installés dans `html/templates/intel` ou `amd`.
5. Apprentissage du nom de disque à partir des images déjà présentes pour le même préfixe, avec profils de secours.
6. Dry-run avant toute écriture.
7. Conversion VMDK/VDI/RAW/QCOW vers QCOW2 avec `qemu-img`.
8. Installation dans les chemins EVE-NG appropriés.
9. Sauvegarde d'un dossier/fichier cible existant avant remplacement.
10. Exécution de `/opt/unetlab/wrappers/unl_wrapper -a fixpermissions`.

## Chemins utilisés

- QEMU: `/opt/unetlab/addons/qemu/<template>-<version>/`
- IOL: `/opt/unetlab/addons/iol/bin/`
- Dynamips: `/opt/unetlab/addons/dynamips/`
- État/uploads: `/var/lib/eve-image-forge/`
- Jeton: `/etc/eve-image-forge/token`

## Limites importantes

Une image ne devient pas automatiquement bootable uniquement parce qu'elle est convertie en QCOW2. Le template EVE-NG doit correspondre au produit (CPU, RAM, NIC, console et options QEMU). L'application réutilise les templates déjà installés dans EVE et permet de choisir explicitement le template et le bus disque.

Pour une ISO, l'application crée `cdrom.iso` et un disque QCOW2 vierge. Il faut ensuite démarrer le noeud, faire l'installation du système sur le disque et, selon le produit/template, retirer l'ISO après installation.

Pour IOL, l'application place et rend le `.bin` exécutable, mais ne fournit aucune image ni licence.

## Service

```bash
systemctl status eve-image-forge
journalctl -u eve-image-forge -f
systemctl restart eve-image-forge
```

## Désinstallation

```bash
sudo ./uninstall.sh
```

Les backups et uploads ne sont pas supprimés automatiquement afin d'éviter une perte de données.
