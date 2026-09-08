# EVE Image Forge 0.2.1 — Smart Import

Application web locale pour préparer et installer des images dans EVE-NG avec détection automatique du produit, du template, de la version et du layout disque.

## Project origin / Origine du projet

**English**  
Original project vision, idea, and concept by **Guillaume Paré**.  
Conceived and initiated by **Guillaume Paré**, with the assistance of artificial intelligence.

**Français**  
Vision, idée et concept originaux du projet par **Guillaume Paré**.  
Conçu et initié par **Guillaume Paré**, avec l'aide de l'intelligence artificielle.

## Interface bilingue FR / EN

L'interface est disponible en français et en anglais. Au premier chargement, EVE Image Forge utilise le français pour un navigateur francophone et l'anglais pour les autres langues. Les boutons `FR` et `EN` dans l'en-tête permettent de changer instantanément de langue et le choix est mémorisé localement dans le navigateur.

La traduction couvre aussi les éléments dynamiques: progression d'upload, Smart Plan, état de la cible, mapping des disques, avertissements, raisons de détection, résultats, erreurs et principaux messages des logs d'installation.

## Nouveauté 0.2: Smart Import

Après l'upload, Smart Import analyse le nom du fichier, les chemins internes d'une archive, les templates réellement présents sur le serveur EVE-NG et les images déjà installées. Il construit ensuite un plan d'installation complet avant toute écriture.

Le plan peut automatiquement proposer:

- le constructeur et le produit;
- le préfixe/template EVE-NG;
- la version extraite du nom de l'image;
- le dossier cible `/opt/unetlab/addons/qemu/<template>-<version>/`;
- le mapping d'un ou plusieurs disques vers `hda.qcow2`, `virtioa.qcow2`, `sataa.qcow2`, etc.;
- la conversion VMDK/VDI/RAW/QCOW vers QCOW2;
- les disques additionnels à générer lorsqu'un profil le requiert;
- la présence d'une version identique ou d'autres versions déjà installées;
- un score de confiance et les raisons de la détection.

Le mode manuel de la version 0.1 reste disponible en tout temps.

## Produits reconnus

Les profils intégrés couvrent notamment Cisco ASAv, Catalyst 8000V/9000V, CSR1000v, IOSv/IOSvL2, NX-OSv 9000, XRv/XRv9K, Firepower FTD/FMC, Cisco SD-WAN/Viptela, Fortinet FortiGate, Palo Alto VM-Series, Check Point, Juniper vSRX/vJunos/vMX/vQFX, F5 BIG-IP, Aruba ClearPass/AOS-CX/VMC, Arista vEOS, VyOS, MikroTik CHR, pfSense, OPNsense, VMware ESXi/vCenter/NSX, Windows, Linux et Nutanix CE/AHV générique.

Smart Import ne dépend pas uniquement de cette liste: il compare aussi la source avec les templates QEMU présents dans `html/templates/intel` ou `html/templates/amd`.

## Formats

- QEMU directs: `.qcow2`, `.qcow`, `.vmdk`, `.vdi`, `.raw`, `.img`
- Installation ISO: `.iso` + création d'un disque QCOW2 vierge
- Cisco IOL: `.bin`
- Dynamips: `.image`
- Archives: `.zip`, `.tgz`, `.tar.gz`, `.tar`, `.ova`, `.gz`

## Installation / mise à jour

Sur le serveur EVE-NG:

```bash
git clone https://github.com/gpareNTNX/eve-ng-importer.git
cd eve-ng-importer
sudo ./install.sh
```

Pour une installation existante:

```bash
cd eve-ng-importer
git pull
sudo ./install.sh
```

Le script affiche l'URL du service sur le port `8088` et le jeton d'accès. Le jeton existant est conservé lors d'une mise à jour.

## Workflow Smart Import

1. Upload par morceaux de 8 MiB.
2. Extraction sécurisée des archives.
3. Inventaire de tous les fichiers QEMU/ISO/IOL/Dynamips.
4. Détection constructeur/produit/version.
5. Comparaison avec les templates installés sur le serveur.
6. Apprentissage du layout disque à partir des images déjà présentes.
7. Construction d'un plan multi-disques.
8. Détection d'une cible déjà installée.
9. Dry-run par défaut.
10. Préparation dans un dossier de staging.
11. Conversion/copie/création des disques.
12. Sauvegarde de l'ancienne cible si nécessaire.
13. Activation atomique du nouveau dossier.
14. Exécution de `/opt/unetlab/wrappers/unl_wrapper -a fixpermissions`.

## Multi-disques

Si l'archive contient plusieurs disques, Smart Import les installe ensemble. Les noms EVE déjà présents dans l'archive sont préservés lorsqu'ils sont valides. Sinon, le layout du template ou le profil intégré est utilisé.

Exemple ClearPass:

```text
ClearPass-disk1.qcow2 -> hda.qcow2
ClearPass-disk2.qcow2 -> hdb.qcow2
```

Exemple vManage classique:

```text
viptela-vmanage-19.2.3.qcow2 -> virtioa.qcow2
[créé automatiquement, 100 Go] -> virtiob.qcow2
```

## Sécurité

- Dry-run activé par défaut.
- Blocage des chemins `../` dans ZIP/TAR.
- Liens symboliques, hard links et devices ignorés dans les archives.
- Validation stricte des noms de disques EVE.
- Maximum de 26 disques dans un plan.
- Taille des disques générés limitée à 1–4096 Go.
- Préparation QEMU dans un répertoire de staging avant remplacement de la cible.
- Sauvegarde de la cible existante dans `/var/lib/eve-image-forge/backups/`.
- Authentification Web par jeton local.

## Limites importantes

Smart Import utilise des heuristiques. Un score de confiance faible doit être vérifié avant de désactiver le dry-run. Le fait qu'une image soit au format QCOW2 ne garantit pas qu'elle soit bootable avec n'importe quel template: CPU, RAM, NIC, console et options QEMU restent définis par le template EVE-NG.

Le profil Nutanix est volontairement générique: Smart Import peut reconnaître le fichier et proposer un préfixe, mais il avertit si aucun template Nutanix correspondant n'est installé dans EVE-NG.

Pour IOL, l'application place et rend le `.bin` exécutable mais ne fournit aucune image ni licence.

## API locale

- `GET /api/status`
- `GET /api/templates`
- `GET /api/installed`
- `POST /api/analyze`
- `POST /api/install`

Toutes les API, sauf les fichiers statiques de l'interface, exigent `X-EIF-Token`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

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
