# Automatiseur de captures d'écran basé sur les commits Git

Vous écrivez des livres techniques, de la documentation ou des tutoriels? Vous connaissez sûrement cette douleur : modifier une ligne de code et devoir refaire des dizaines de captures d'écran manuellement.

J'en avais marre. Alors j'ai codé un outil pour automatiser tout ça.

## Démonstration vidéo des fonctionnalités de l'outil

<https://youtu.be/mr1tle2KB4o>

## Installation

```shell
python3 -m venv .venv
source ./venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Comment ça marche ?

L'idée est simple : chaque fois que votre projet atteint un état que vous voulez capturer, vous faites un commit avec un tag spécial :

```shell
git commit -m "[screenshot:home-page,about-page] Description"
```

Le script va ensuite :
1. Parcourir votre historique Git
2. Se positionner sur chaque commit taggé
3. Lancer votre serveur automatiquement
4. Prendre les captures d'écran
5. Les nommer et organiser correctement

Résultat : des dizaines de captures générées en quelques minutes, sans intervention manuelle.

## Technologies utilisées :

- Python: Le langage du script
- Playwright: Pour contrôler le navigateur et prendre les captures
- GitPython: Pour naviguer dans l'historique Git
- Pillow: Pour ajouter une barre de titre style navigateur (optionnel)

## Comment l'utiliser ?

À chaque étape importante du projet, commiter avec un tag spécial :

```shell
git commit -m "[screenshot:default-welcome-page] Page d'accueil par défaut"
git commit -m "[screenshot:first-response] Premier contrôleur"
git commit -m "[screenshot:home-styled] Page stylisée avec Tailwind"
git commit -m "[screenshot:home-page] Page d'accueil terminée"

# Plusieurs captures dans le même commit
git commit -m "[screenshot:home-page,about-page,contact-page] Pages principales terminées"

# Avec espaces (les espaces sont ignorés)
git commit -m "[screenshot:home-page, about-page, contact-page] Pages principales"
```

Puis générer toutes les captures :

```shell
# Lister toutes les captures disponibles
python screenshotter.py ~/symfony-book/projects/hello-world --list

# Générer TOUTES les captures
python screenshotter.py ~/symfony-book/projects/hello-world

# Avec un fichier de configuration
python screenshotter.py ~/symfony-book/projects/hello-world -c hello_world.yaml

# Générer seulement certaines captures
python screenshotter.py ~/symfony-book/projects/hello-world --only home-page about-page

# Mode debug (voir le navigateur)
python screenshotter.py ~/symfony-book/projects/hello-world --no-headless
```

## Les options show_title_bar et title_bar_style

L'option `show_title_bar: true` permet d'ajouter une barre de titre et une barre d'adresse à la capture d'écran.

Vous pouvez modifier le style de le barre de titre grâce à l'option `title_bar_style`.

Les styles supportés sont les suivants :

| Style | Description |
|-------|-------------|
| `chrome` | Barre grise avec boutons rouge/jaune/vert, titre centré, barre d'URL |
| `safari` | Style macOS Safari, plus compact |
| `minimal` | Très épuré, hauteur réduite |

### Résultat visuel

```
┌─────────────────────────────────────────────────────┐
│  ● ● ●          Hello City - Accueil                │  <- Boutons + Titre
│         ┌─────────────────────────────────┐         │
│         │  http://127.0.0.1:8000/         │         │  <- Barre d'URL
│         └─────────────────────────────────┘         │
├─────────────────────────────────────────────────────┤
│                                                     │
│              (Contenu de la page)                   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## L'option full_page

L'option `full_page` dans Playwright permet de capturer toute la page (même les parties qui nécessitent de scroller), et pas seulement ce qui est visible dans le viewport.

### Comparaison

#### `full_page: false` (par défaut)

Capture uniquement ce qui est visible dans la fenêtre (viewport) :

```
┌─────────────────────┐
│                     │
│  Partie visible     │  <- Capturé
│                     │
└─────────────────────┘
│                     │
│  Partie cachée      │  <- NON capturé (il faut scroller)
│  (sous le fold)     │
│                     │
└─────────────────────┘
```

#### `full_page: true`

Capture toute la page, peu importe sa longueur :

```
┌─────────────────────┐
│                     │
│  Partie visible     │  <- Capturé
│                     │
├─────────────────────┤
│                     │
│  Partie cachée      │  <- Capturé aussi !
│  (sous le fold)     │
│                     │
└─────────────────────┘
```

## Les options wait_for et delay

### wait_for

L'option wait_for permet d'attendre qu'un élément dynamique soit ajouté au DOM

```yaml
screenshots_config:
  # Attendre que le contenu principal soit chargé
  home-page:
    url: /
    wait_for: '.main-content'

  # Attendre qu'un tableau de données soit rendu
  data-table:
    url: /users
    wait_for: 'table tbody tr'
```

### delay

L'option delay permet de laisser du temps pour le rendu

```yaml
screenshots_config:
  # Charger la librairie X peut prendre du temps
  styled-page:
    url: /
    delay: 2.0 # Attendre 2 secondes

  # Animations CSS
  animated-page:
    url: /welcome
    delay: 1.5 # Laisser l'animation se terminer

  # Page simple, pas besoin d'attendre longtemps
  simple-page:
    url: /about
    delay: 0.5 # Valeur par défaut
```

### Combiner les deux options

```yaml
screenshots_config:
  dashboard:
    url: /dashboard
    wait_for: '.chart-container' # Attendre que le graphique soit dans le DOM
    delay: 1.0 # Puis attendre 1s pour le rendu complet
```
