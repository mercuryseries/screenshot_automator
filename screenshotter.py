#!/usr/bin/env python3
"""
Automatiseur de captures d'écran basé sur les commits Git
=========================================================

Ce script utilise les commits Git pour naviguer entre les différents états
du projet et prendre les captures d'écran correspondantes.

CONCEPT:
- Chaque capture d'écran correspond à un commit Git spécifique
- Le script checkout le commit, prend la capture, puis passe au suivant
- Les commits sont tagués avec le nom de la capture (ex: [screenshot:home-styled])

WORKFLOW RECOMMANDÉ:
1. Développer le projet normalement
2. À chaque étape importante, faire un commit avec un message spécial:
   git commit -m "[screenshot:nom-capture] Description de l'étape"
3. Lancer ce script pour générer toutes les captures automatiquement

Dépendances:
    pip install playwright pyyaml gitpython pillow
    playwright install chromium
"""

import os
import sys
import re
import yaml
import subprocess
import time
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print(
        "⚠️ Playwright non disponible. Installez avec: pip install playwright && playwright install chromium"
    )

try:
    import git

    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    print("⚠️ GitPython non disponible. Installez avec: pip install gitpython")

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ Pillow non disponible. Installez avec: pip install pillow")


@dataclass
class ScreenshotSpec:
    """Spécification d'une capture d'écran"""

    name: str
    commit_sha: str
    commit_message: str
    url: str = "/"
    output_path: str = ""
    viewport_width: int = 1280
    viewport_height: int = 800
    full_page: bool = False
    wait_for: Optional[str] = None
    delay: float = 1.0
    is_error_page: bool = False
    description: str = ""
    show_title_bar: bool = False  # Afficher une barre de titre style navigateur
    title_bar_style: str = "chrome"  # Style: "chrome", "safari", "minimal"

    def __post_init__(self):
        if not self.output_path:
            self.output_path = f"screenshots/{self.name}.png"


@dataclass
class CommitScreenshots:
    """Groupe de captures pour un même commit"""

    commit_sha: str
    commit_message: str
    screenshots: List[ScreenshotSpec] = field(default_factory=list)
    description: str = ""
    index: int = 0  # Index du commit (01, 02, 03, ...)


class TitleBarRenderer:
    """Ajoute une barre de titre style navigateur aux captures d'écran"""

    # Couleurs pour les différents styles
    STYLES = {
        "chrome": {
            "bg_color": (222, 225, 230),  # Gris clair Chrome
            "title_color": (60, 64, 67),  # Gris foncé pour le texte
            "url_bg": (255, 255, 255),  # Blanc pour la barre d'URL
            "url_color": (95, 99, 104),  # Gris pour l'URL
            "button_colors": [
                (237, 106, 94),
                (245, 191, 79),
                (98, 197, 84),
            ],  # Rouge, Jaune, Vert
            "height": 72,
            "url_bar_height": 32,
        },
        "safari": {
            "bg_color": (244, 244, 244),
            "title_color": (0, 0, 0),
            "url_bg": (255, 255, 255),
            "url_color": (128, 128, 128),
            "button_colors": [(255, 95, 87), (255, 189, 46), (39, 201, 63)],
            "height": 52,
            "url_bar_height": 28,
        },
        "minimal": {
            "bg_color": (248, 249, 250),
            "title_color": (33, 37, 41),
            "url_bg": (255, 255, 255),
            "url_color": (108, 117, 125),
            "button_colors": [(255, 95, 87), (255, 189, 46), (39, 201, 63)],
            "height": 40,
            "url_bar_height": 24,
        },
    }

    def __init__(self):
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow est requis pour les barres de titre")

    def add_title_bar(
        self, image_path: str, title: str, url: str, style: str = "chrome"
    ) -> str:
        """
        Ajoute une barre de titre à une image existante.

        Args:
            image_path: Chemin vers l'image de capture
            title: Titre de la page (balise <title>)
            url: URL affichée dans la barre d'adresse
            style: Style de la barre ('chrome', 'safari', 'minimal')

        Returns:
            Chemin vers l'image modifiée (même chemin, fichier écrasé)
        """
        style_config = self.STYLES.get(style, self.STYLES["chrome"])

        # Ouvrir l'image originale
        original = Image.open(image_path)
        original_width, original_height = original.size

        # Créer une nouvelle image avec espace pour la barre de titre
        bar_height = style_config["height"]
        new_height = original_height + bar_height
        new_image = Image.new(
            "RGB", (original_width, new_height), style_config["bg_color"]
        )

        # Dessiner la barre de titre
        draw = ImageDraw.Draw(new_image)

        # Charger une police (ou utiliser la police par défaut)
        try:
            # Essayer différentes polices système
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "C:\\Windows\\Fonts\\segoeui.ttf",
            ]
            title_font = None
            url_font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    title_font = ImageFont.truetype(font_path, 14)
                    url_font = ImageFont.truetype(font_path, 12)
                    break
            if not title_font:
                title_font = ImageFont.load_default()
                url_font = ImageFont.load_default()
        except:
            title_font = ImageFont.load_default()
            url_font = ImageFont.load_default()

        # Dessiner les boutons de fenêtre (rouge, jaune, vert)
        button_y = 14
        button_x = 16
        button_radius = 6
        button_spacing = 20

        for i, color in enumerate(style_config["button_colors"]):
            x = button_x + i * button_spacing
            draw.ellipse(
                [
                    x - button_radius,
                    button_y - button_radius,
                    x + button_radius,
                    button_y + button_radius,
                ],
                fill=color,
            )

        # Dessiner le titre centré
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (original_width - title_width) // 2
        title_y = 10
        draw.text(
            (title_x, title_y), title, fill=style_config["title_color"], font=title_font
        )

        # Dessiner la barre d'URL
        url_bar_y = 34
        url_bar_height = style_config["url_bar_height"]
        url_bar_margin = 80
        url_bar_radius = url_bar_height // 2

        # Fond de la barre d'URL (rectangle arrondi simulé)
        draw.rounded_rectangle(
            [
                url_bar_margin,
                url_bar_y,
                original_width - url_bar_margin,
                url_bar_y + url_bar_height,
            ],
            radius=url_bar_radius,
            fill=style_config["url_bg"],
        )

        # Texte de l'URL centré dans la barre
        url_bbox = draw.textbbox((0, 0), url, font=url_font)
        url_text_width = url_bbox[2] - url_bbox[0]
        url_x = (original_width - url_text_width) // 2
        url_y = url_bar_y + (url_bar_height - (url_bbox[3] - url_bbox[1])) // 2
        draw.text((url_x, url_y), url, fill=style_config["url_color"], font=url_font)

        # Coller l'image originale en dessous de la barre
        new_image.paste(original, (0, bar_height))

        # Sauvegarder
        new_image.save(image_path, quality=95)
        original.close()

        return image_path

    def extract_page_title(self, page) -> str:
        """Extrait le titre de la page depuis Playwright"""
        try:
            return page.title() or "Sans titre"
        except:
            return "Sans titre"


class GitProjectManager:
    """Gère les états du projet via Git"""

    # Pattern pour capturer un ou plusieurs noms séparés par des virgules
    # Ex: [screenshot:home-page] ou [screenshot:home-page,about-page,contact-page]
    SCREENSHOT_PATTERN = re.compile(r"\[screenshot:([^\]]+)\]")

    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        if not GIT_AVAILABLE:
            raise RuntimeError("GitPython est requis")
        self.repo = git.Repo(self.project_path)
        self.original_branch = self.repo.active_branch.name
        self.original_commit = self.repo.head.commit.hexsha

    def get_screenshot_commits(self) -> List[CommitScreenshots]:
        """Récupère tous les commits marqués pour capture, groupés par commit"""
        commits_with_screenshots = []

        for commit in self.repo.iter_commits():
            match = self.SCREENSHOT_PATTERN.search(commit.message)
            if match:
                # Extraire les noms de captures (peut être "nom1,nom2,nom3")
                screenshot_names_str = match.group(1)
                screenshot_names = [
                    name.strip() for name in screenshot_names_str.split(",")
                ]

                # Créer un ScreenshotSpec pour chaque nom
                specs = []
                for name in screenshot_names:
                    specs.append(
                        ScreenshotSpec(
                            name=name,
                            commit_sha=commit.hexsha,
                            commit_message=commit.message,
                            description=commit.message.split("\n")[0],
                        )
                    )

                commits_with_screenshots.append(
                    CommitScreenshots(
                        commit_sha=commit.hexsha,
                        commit_message=commit.message,
                        screenshots=specs,
                        description=commit.message.split("\n")[0],
                    )
                )

        # Inverser pour avoir l'ordre chronologique
        commits_with_screenshots.reverse()

        # Ajouter l'index du commit (01, 02, 03, ...) à chaque CommitScreenshots
        for index, commit_group in enumerate(commits_with_screenshots, start=1):
            commit_group.index = index

        return commits_with_screenshots

    def get_all_screenshot_specs(self) -> List[ScreenshotSpec]:
        """Récupère toutes les captures à plat (pour compatibilité)"""
        all_specs = []
        for commit_group in self.get_screenshot_commits():
            all_specs.extend(commit_group.screenshots)
        return all_specs

    def checkout_commit(self, sha: str):
        """Se positionne sur un commit spécifique"""
        self.repo.git.checkout(sha)
        print(f"  → Checkout: {sha[:8]}")

    def restore_original(self):
        """Restaure l'état original"""
        self.repo.git.checkout(self.original_branch)
        print(f"✓ Restauré sur: {self.original_branch}")

    def get_files_at_commit(self, sha: str) -> Dict[str, str]:
        """Récupère le contenu des fichiers à un commit donné"""
        commit = self.repo.commit(sha)
        files = {}
        for blob in commit.tree.traverse():
            if blob.type == "blob":
                try:
                    files[blob.path] = blob.data_stream.read().decode("utf-8")
                except:
                    pass
        return files


class SymfonyServer:
    """Gère le serveur de développement Symfony"""

    def __init__(self, project_path: str, port: int = 8000):
        self.project_path = Path(project_path)
        self.port = port
        self.process = None
        self.base_url = f"http://127.0.0.1:{port}"

    def start(self):
        """Démarre le serveur"""
        if self.process:
            return

        self.process = subprocess.Popen(
            ["php", "-S", f"127.0.0.1:{self.port}", "-t", "public/"],
            cwd=self.project_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        print(f"✓ Serveur démarré sur {self.base_url}")

    def stop(self):
        """Arrête le serveur"""
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
            print("✓ Serveur arrêté")

    def restart(self):
        """Redémarre le serveur (utile après un changement de code)"""
        self.stop()
        time.sleep(1)
        self.start()

    def clear_cache(self):
        """Vide le cache Symfony"""
        cache_dir = self.project_path / "var" / "cache"
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            print("  → Cache vidé")


class BrowserCapture:
    """Capture les pages web avec Playwright"""

    def __init__(self):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright est requis")
        self.playwright = None
        self.browser = None
        self.context = None

    def start(self, headless: bool = True):
        """Démarre le navigateur"""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=2,  # Qualité retina
        )
        self.title_bar_renderer = TitleBarRenderer() if PIL_AVAILABLE else None
        print("✓ Navigateur démarré")

    def capture(self, spec: ScreenshotSpec, base_url: str) -> str:
        """Prend une capture d'écran"""
        page = self.context.new_page()
        page.set_viewport_size(
            {"width": spec.viewport_width, "height": spec.viewport_height}
        )

        url = spec.url if spec.url.startswith("http") else f"{base_url}{spec.url}"

        try:
            page.goto(url, wait_until="networkidle", timeout=10000)
        except Exception as e:
            if spec.is_error_page:
                # C'est normal pour les pages d'erreur
                pass
            else:
                print(f"  ⚠️ Erreur de chargement: {e}")

        if spec.wait_for:
            try:
                page.wait_for_selector(spec.wait_for, timeout=5000)
            except:
                pass

        time.sleep(spec.delay)

        # Récupérer le titre de la page AVANT de fermer
        page_title = page.title() or "Sans titre"

        output_path = Path(spec.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        page.screenshot(path=str(output_path), full_page=spec.full_page)

        page.close()

        # Ajouter la barre de titre si demandé
        if spec.show_title_bar:
            if self.title_bar_renderer:
                try:
                    self.title_bar_renderer.add_title_bar(
                        image_path=str(output_path),
                        title=page_title,
                        url=url,
                        style=spec.title_bar_style,
                    )
                    print(
                        f"    🏷️  Barre de titre ajoutée (style: {spec.title_bar_style})"
                    )
                except Exception as e:
                    print(f"    ⚠️ Erreur lors de l'ajout de la barre de titre: {e}")
            else:
                print("    ⚠️ Barre de titre demandée mais Pillow non disponible")

        return str(output_path)

    def stop(self):
        """Ferme le navigateur"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


class ScreenshotOrchestrator:
    """Orchestre la génération de toutes les captures"""

    def __init__(self, project_path: str, config_path: Optional[str] = None):
        self.project_path = Path(project_path).resolve()
        self.config = self._load_config(config_path) if config_path else {}

        self.git_manager = GitProjectManager(project_path)
        self.server = SymfonyServer(project_path)
        self.browser = BrowserCapture()

        self.results = []

    def _load_config(self, path: str) -> dict:
        """Charge la configuration YAML"""
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def setup(self, headless: bool = True):
        """Initialise tous les composants"""
        self.browser.start(headless=headless)
        self.server.start()

    def teardown(self):
        """Nettoie les ressources"""
        self.browser.stop()
        self.server.stop()
        self.git_manager.restore_original()

    def run_from_git(self, only: List[str] = None):
        """Exécute les captures basées sur les commits Git"""
        commit_groups = self.git_manager.get_screenshot_commits()

        if not commit_groups:
            print("Aucun commit marqué pour capture trouvé.")
            print(
                "Utilisez le format: git commit -m '[screenshot:nom-capture] Description'"
            )
            print(
                "Ou pour plusieurs captures: git commit -m '[screenshot:capture1,capture2,capture3] Description'"
            )
            return

        # Compter le total de captures
        total_screenshots = sum(len(cg.screenshots) for cg in commit_groups)
        print(
            f"\n📸 {total_screenshots} captures à faire ({len(commit_groups)} commits)\n"
        )

        screenshot_index = 0
        for commit_group in commit_groups:
            # Filtrer les captures si --only est spécifié
            screenshots_to_take = commit_group.screenshots
            if only:
                screenshots_to_take = [s for s in screenshots_to_take if s.name in only]

            if not screenshots_to_take:
                continue

            # Préfixe basé sur l'index du commit (01_, 02_, etc.)
            commit_prefix = f"{commit_group.index:02d}_"

            # Checkout le commit une seule fois pour toutes les captures de ce commit
            print(f"\n{'=' * 60}")
            print(
                f"[{commit_prefix[:-1]}] Commit: {commit_group.commit_sha[:8]} - {commit_group.description[:40]}"
            )
            print(f"Captures: {', '.join(s.name for s in screenshots_to_take)}")
            print(f"{'=' * 60}")

            try:
                self.git_manager.checkout_commit(commit_group.commit_sha)

                # Vider le cache et redémarrer le serveur une seule fois par commit
                self.server.clear_cache()
                self.server.restart()

                # Prendre chaque capture pour ce commit
                for spec in screenshots_to_take:
                    screenshot_index += 1
                    print(f"\n  [{screenshot_index}/{total_screenshots}] {spec.name}")

                    try:
                        # Appliquer la config spécifique si elle existe
                        self._apply_screenshot_config(spec)

                        # Générer le chemin de sortie avec préfixe
                        spec.output_path = self._generate_output_path(
                            spec, commit_prefix
                        )

                        # Prendre la capture
                        path = self.browser.capture(spec, self.server.base_url)

                        self.results.append(
                            {
                                "name": spec.name,
                                "filename": f"{commit_prefix}{spec.name}.png",
                                "path": path,
                                "commit": commit_group.commit_sha[:8],
                                "commit_index": commit_group.index,
                                "status": "success",
                            }
                        )
                        print(f"    ✓ Sauvegardé: {path}")

                    except Exception as e:
                        self.results.append(
                            {
                                "name": spec.name,
                                "filename": f"{commit_prefix}{spec.name}.png",
                                "path": None,
                                "commit": commit_group.commit_sha[:8],
                                "commit_index": commit_group.index,
                                "status": "error",
                                "error": str(e),
                            }
                        )
                        print(f"    ✗ Erreur: {e}")

            except Exception as e:
                print(f"  ✗ Erreur lors du checkout: {e}")
                # Marquer toutes les captures de ce commit comme échouées
                for spec in screenshots_to_take:
                    self.results.append(
                        {
                            "name": spec.name,
                            "filename": f"{commit_prefix}{spec.name}.png",
                            "path": None,
                            "commit": commit_group.commit_sha[:8],
                            "commit_index": commit_group.index,
                            "status": "error",
                            "error": f"Checkout failed: {e}",
                        }
                    )

    def _generate_output_path(self, spec: ScreenshotSpec, commit_prefix: str) -> str:
        """Génère le chemin de sortie avec le préfixe du commit"""
        output_dir = self.config.get("output_dir", "screenshots")

        # Vérifier si une config spécifique définit un output personnalisé
        screenshots_config = self.config.get("screenshots", {})
        if spec.name in screenshots_config:
            custom_output = screenshots_config[spec.name].get("output")
            if custom_output:
                # Ajouter le préfixe au nom de fichier personnalisé
                path = Path(custom_output)
                new_filename = f"{commit_prefix}{path.stem}{path.suffix}"
                return str(path.parent / new_filename)

        # Sinon, utiliser le répertoire par défaut
        return f"{output_dir}/{commit_prefix}{spec.name}.png"

    def _apply_screenshot_config(self, spec: ScreenshotSpec):
        """Applique la configuration spécifique à une capture"""
        # D'abord, appliquer la config globale par défaut
        global_config = self.config.get("defaults", {})
        if "show_title_bar" in global_config:
            spec.show_title_bar = global_config["show_title_bar"]
        if "title_bar_style" in global_config:
            spec.title_bar_style = global_config["title_bar_style"]

        # Ensuite, appliquer la config spécifique à cette capture (qui peut override)
        screenshots_config = self.config.get("screenshots", {})
        if spec.name in screenshots_config:
            cfg = screenshots_config[spec.name]
            if "url" in cfg:
                spec.url = cfg["url"]
            if "viewport_width" in cfg:
                spec.viewport_width = cfg["viewport_width"]
            if "viewport_height" in cfg:
                spec.viewport_height = cfg["viewport_height"]
            if "full_page" in cfg:
                spec.full_page = cfg["full_page"]
            if "wait_for" in cfg:
                spec.wait_for = cfg["wait_for"]
            if "delay" in cfg:
                spec.delay = cfg["delay"]
            if "output" in cfg:
                spec.output_path = cfg["output"]
            if "show_title_bar" in cfg:
                spec.show_title_bar = cfg["show_title_bar"]
            if "title_bar_style" in cfg:
                spec.title_bar_style = cfg["title_bar_style"]

            print(
                f"    📋 Config appliquée: url={spec.url}, show_title_bar={spec.show_title_bar}"
            )
        else:
            print(f"    📋 Pas de config spécifique pour '{spec.name}'")

    def _apply_required_files(self, files: List[dict]):
        """Applique les fichiers requis pour une capture"""
        for file_spec in files:
            path = self.project_path / file_spec["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file_spec["content"], encoding="utf-8")
            print(f"  → Fichier créé: {file_spec['path']}")

    def generate_report(self) -> str:
        """Génère un rapport des captures"""
        report = [
            "# Rapport de captures d'écran",
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"Total: {len(self.results)} captures",
            f"Succès: {sum(1 for r in self.results if r['status'] == 'success')}",
            f"Erreurs: {sum(1 for r in self.results if r['status'] == 'error')}",
            "",
            "## Détails",
            "",
        ]

        for r in self.results:
            if r["status"] == "success":
                report.append(f"- ✓ **{r['name']}**: `{r['path']}`")
            else:
                report.append(f"- ✗ **{r['name']}**: {r.get('error', 'Unknown error')}")

        return "\n".join(report)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Automatise les captures d'écran pour un livre Symfony (basé sur Git)"
    )
    parser.add_argument("project_path", help="Chemin vers le projet Symfony")
    parser.add_argument(
        "-c", "--config", help="Fichier de configuration YAML (optionnel)"
    )
    parser.add_argument(
        "--only", nargs="+", help="Capturer seulement ces screenshots (par nom)"
    )
    parser.add_argument(
        "--list", action="store_true", help="Lister les captures disponibles"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Afficher le navigateur (utile pour debug)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.project_path):
        print(f"Erreur: Projet non trouvé: {args.project_path}")
        sys.exit(1)

    orchestrator = ScreenshotOrchestrator(args.project_path, args.config)

    if args.list:
        commit_groups = orchestrator.git_manager.get_screenshot_commits()
        total = sum(len(cg.screenshots) for cg in commit_groups)
        print(
            f"Captures disponibles ({total} captures dans {len(commit_groups)} commits):\n"
        )
        for cg in commit_groups:
            prefix = f"{cg.index:02d}_"
            print(
                f"  [{prefix[:-1]}] Commit {cg.commit_sha[:8]}: {cg.description[:45]}"
            )
            for spec in cg.screenshots:
                print(f"       → {prefix}{spec.name}.png")
        sys.exit(0)

    try:
        orchestrator.setup(headless=not args.no_headless)

        orchestrator.run_from_git(args.only)

        print("\n" + orchestrator.generate_report())

    finally:
        orchestrator.teardown()


if __name__ == "__main__":
    main()
