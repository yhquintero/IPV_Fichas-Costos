"""Contrast regression checks for shared web/Android secondary-text tokens.

These assertions cover the declared text tokens against base surfaces only; they
are not a full WCAG audit of every component, state, image, or device rendering.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    channels = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    return tuple(
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )


def _luminance(hex_color: str) -> float:
    red, green, blue = _rgb(hex_color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _css_tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;", block))


class SecondaryTextContrastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        light_match = re.search(r":root\s*\{([^}]*)\}", css)
        dark_match = re.search(r'\[data-theme="dark"\]\s*\{([^}]*)\}', css)
        if not light_match or not dark_match:
            raise AssertionError("No se pudieron localizar los tokens de tema de la interfaz web")
        cls.light = _css_tokens(light_match.group(1))
        cls.dark = _css_tokens(dark_match.group(1))

        kotlin = (ROOT / "android" / "app/src/main/java/cu/ipvcostos/app/MainActivity.kt").read_text(
            encoding="utf-8"
        )
        muted = re.search(r"private val MUTED\s*=\s*0xFF([0-9a-fA-F]{6})", kotlin)
        if not muted:
            raise AssertionError("No se encontró el token MUTED de Android")
        cls.android_muted = f"#{muted.group(1)}"

    def assert_text_contrast(self, foreground: str, surfaces: tuple[str, ...], theme: str) -> None:
        for surface in surfaces:
            with self.subTest(theme=theme, foreground=foreground, surface=surface):
                self.assertGreaterEqual(
                    _contrast_ratio(foreground, surface),
                    4.5,
                    f"Contraste insuficiente para {theme}: {foreground} sobre {surface}",
                )

    def test_web_light_secondary_text_tokens_meet_wcag_aa_for_base_surfaces(self) -> None:
        for token in ("--text-3", "--text-4"):
            self.assertIn(token, self.light)
            self.assert_text_contrast(self.light[token], ("#ffffff", self.light["--surface-2"]), "web claro")

    def test_web_dark_secondary_text_tokens_meet_wcag_aa_for_base_surfaces(self) -> None:
        for token in ("--text-3", "--text-4"):
            self.assertIn(token, self.dark)
            self.assert_text_contrast(self.dark[token], (self.dark["--surface"], self.dark["--surface-2"]), "web oscuro")

    def test_android_muted_text_meets_wcag_aa_for_base_surfaces(self) -> None:
        self.assert_text_contrast(self.android_muted, ("#ffffff", "#f6f8f5"), "Android")


if __name__ == "__main__":
    unittest.main()
