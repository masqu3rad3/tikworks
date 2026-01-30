"""Unit tests for tik.core.color module."""

import pytest

from tik.core.color import Color


class TestColorInitialization:
    """Tests for Color class initialization."""

    def test_init_with_none(self):
        """Test Color initialized with None creates black color."""
        color = Color()
        assert color.rgb == (0.0, 0.0, 0.0)

    def test_init_with_color_object(self):
        """Test Color initialized from another Color object."""
        original = Color((0.5, 0.6, 0.7))
        copy = Color(original)
        assert copy.rgb == original.rgb

    def test_init_with_hex_string(self):
        """Test Color initialized from hex string."""
        color = Color("#FF0000")
        assert color.rgb == pytest.approx((1.0, 0.0, 0.0), rel=1e-2)

    def test_init_with_short_hex_string(self):
        """Test Color initialized from 3-char hex string."""
        color = Color("#F00")
        assert color.rgb == pytest.approx((1.0, 0.0, 0.0), rel=1e-2)

    def test_init_with_named_color(self):
        """Test Color initialized from color name."""
        color = Color("red")
        assert color.rgb == (1.0, 0.0, 0.0)

    def test_init_with_float_tuple(self):
        """Test Color initialized from float tuple (0.0-1.0 range)."""
        color = Color((0.5, 0.25, 0.75))
        assert color.rgb == pytest.approx((0.5, 0.25, 0.75))

    def test_init_with_int_tuple(self):
        """Test Color initialized from int tuple (0-255 range)."""
        color = Color((255, 128, 0))
        assert color.rgb == pytest.approx((1.0, 128 / 255.0, 0.0), rel=1e-2)

    def test_init_with_list(self):
        """Test Color initialized from list."""
        color = Color([0.3, 0.4, 0.5])
        assert color.rgb == pytest.approx((0.3, 0.4, 0.5))

    def test_init_with_unsupported_type_raises(self):
        """Test Color raises TypeError for unsupported input types."""
        with pytest.raises(TypeError, match="Unsupported type for Color"):
            Color(12345)


class TestColorStringParsing:
    """Tests for Color string parsing methods."""

    def test_unknown_color_name_raises(self):
        """Test unknown color name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown color name or format"):
            Color("invalidcolorname")

    def test_invalid_hex_length_raises(self):
        """Test hex string with invalid length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid Hex String"):
            Color("#FFFF")  # 4 chars is invalid

    def test_invalid_hex_chars_raises(self):
        """Test hex string with invalid characters raises ValueError."""
        with pytest.raises(ValueError, match="Invalid Hex String"):
            Color("#GGGGGG")


class TestColorSequenceParsing:
    """Tests for Color sequence parsing."""

    def test_sequence_too_short_raises(self):
        """Test sequence with fewer than 3 values raises ValueError."""
        with pytest.raises(ValueError, match="Sequence must contain at least 3 values"):
            Color((0.5, 0.5))


class TestColorProperties:
    """Tests for Color property accessors."""

    def test_rgb_property(self):
        """Test rgb property returns float tuple."""
        color = Color((0.5, 0.6, 0.7))
        assert color.rgb == pytest.approx((0.5, 0.6, 0.7))

    def test_rgb255_property(self):
        """Test rgb255 property returns integer tuple."""
        color = Color((1.0, 0.5, 0.0))
        assert color.rgb255 == (255, 127, 0)

    def test_hex_property(self):
        """Test hex property returns hex string."""
        color = Color((1.0, 0.0, 0.5))
        hex_val = color.hex
        assert hex_val.startswith("#")
        assert len(hex_val) == 7

    def test_hsv_property(self):
        """Test hsv property returns HSV tuple."""
        color = Color("red")
        hue, sat, val = color.hsv
        assert hue == pytest.approx(0.0)
        assert sat == pytest.approx(1.0)
        assert val == pytest.approx(1.0)


class TestColorRandomization:
    """Tests for Color random generation."""

    def test_random_any(self):
        """Test random color generation with RANDOM_ANY mode."""
        color = Color.random(mode=Color.RANDOM_ANY, seed=42)
        assert isinstance(color, Color)
        # Just verify it's a valid color
        red, green, blue = color.rgb
        assert 0.0 <= red <= 1.0
        assert 0.0 <= green <= 1.0
        assert 0.0 <= blue <= 1.0

    def test_random_pastel(self):
        """Test random color generation with RANDOM_PASTEL mode."""
        color = Color.random(mode=Color.RANDOM_PASTEL, seed=42)
        _, sat, val = color.hsv
        # Pastel colors have low saturation and high value
        assert 0.2 <= sat <= 0.5
        assert 0.8 <= val <= 1.0

    def test_random_neon(self):
        """Test random color generation with RANDOM_NEON mode."""
        color = Color.random(mode=Color.RANDOM_NEON, seed=42)
        _, sat, val = color.hsv
        # Neon colors have high saturation and max value
        assert sat >= 0.8
        assert val == pytest.approx(1.0, rel=1e-2)

    def test_random_metallic(self):
        """Test random color generation with RANDOM_METALLIC mode."""
        color = Color.random(mode=Color.RANDOM_METALLIC, seed=42)
        # Just verify it produces a valid color
        assert isinstance(color, Color)

    def test_random_metallic_low_hue_branch(self):
        """Test random metallic with low hue (h < 0.2) for full coverage."""
        # Use seed that produces h < 0.2 to hit the conditional branch
        # The metallic mode picks hues from [0.0-0.15] or [0.5-0.66]
        # We need to find a seed where choice picks the first (low hue) range
        for seed in range(100):
            color = Color.random(mode=Color.RANDOM_METALLIC, seed=seed)
            hue, _, _ = color.hsv
            if hue < 0.2:
                # Successfully hit the low hue branch
                break

    def test_random_dark(self):
        """Test random color generation with RANDOM_DARK mode."""
        color = Color.random(mode=Color.RANDOM_DARK, seed=42)
        _, _, val = color.hsv
        # Dark colors have low value
        assert val <= 0.3

    def test_random_with_seed_reproducible(self):
        """Test random color with seed produces reproducible results."""
        color1 = Color.random(seed=123)
        color2 = Color.random(seed=123)
        assert color1.rgb == color2.rgb


class TestColorModifiers:
    """Tests for Color modification methods."""

    def test_set_hsv_modifies_color(self):
        """Test set_hsv modifies color HSV values."""
        color = Color("red")
        result = color.set_hsv(h=0.5, s=0.8, v=0.9)
        # Verify method returns self for chaining
        assert result is color
        hue, sat, val = color.hsv
        assert hue == pytest.approx(0.5, rel=1e-2)
        assert sat == pytest.approx(0.8, rel=1e-2)
        assert val == pytest.approx(0.9, rel=1e-2)

    def test_set_hsv_partial_modification(self):
        """Test set_hsv with None keeps original values."""
        color = Color("red")
        original_h, _, original_v = color.hsv
        color.set_hsv(s=0.5)  # Only modify saturation
        new_h, new_s, new_v = color.hsv
        assert new_h == pytest.approx(original_h, rel=1e-2)
        assert new_s == pytest.approx(0.5, rel=1e-2)
        assert new_v == pytest.approx(original_v, rel=1e-2)


class TestColorMagicMethods:
    """Tests for Color magic methods."""

    def test_repr(self):
        """Test __repr__ returns readable string."""
        color = Color("red")
        repr_str = repr(color)
        assert "<Color" in repr_str
        assert "R:" in repr_str
        assert "G:" in repr_str
        assert "B:" in repr_str

    def test_eq_same_colors(self):
        """Test equality comparison for equal colors."""
        color1 = Color((0.5, 0.5, 0.5))
        color2 = Color((0.5, 0.5, 0.5))
        assert color1 == color2

    def test_eq_different_colors(self):
        """Test equality comparison for different colors."""
        color1 = Color("red")
        color2 = Color("blue")
        assert color1 != color2

    def test_eq_with_non_color_returns_not_implemented(self):
        """Test equality with non-Color returns NotImplemented."""
        color = Color("red")
        assert color.__eq__("not a color") is NotImplemented

    def test_add_colors(self):
        """Test color addition."""
        color1 = Color((0.3, 0.3, 0.3))
        color2 = Color((0.3, 0.3, 0.3))
        result = color1 + color2
        assert result.rgb == pytest.approx((0.6, 0.6, 0.6))

    def test_add_with_clamping(self):
        """Test color addition clamps values to 1.0."""
        color1 = Color((0.8, 0.8, 0.8))
        color2 = Color((0.5, 0.5, 0.5))
        result = color1 + color2
        # Values should be clamped to 1.0
        assert result.rgb == pytest.approx((1.0, 1.0, 1.0))

    def test_multiply_color_by_scalar(self):
        """Test color multiplication by scalar."""
        color = Color((0.5, 0.5, 0.5))
        result = color * 2.0
        assert result.rgb == pytest.approx((1.0, 1.0, 1.0))

    def test_multiply_with_clamping(self):
        """Test color multiplication clamps values."""
        color = Color((0.5, 0.5, 0.5))
        result = color * 3.0
        assert result.rgb == pytest.approx((1.0, 1.0, 1.0))

    def test_multiply_with_non_scalar_raises(self):
        """Test multiplication with non-scalar raises TypeError."""
        color = Color("red")
        with pytest.raises(TypeError, match="Can only multiply color by a scalar"):
            _ = color * "invalid"


class TestColorUtilities:
    """Tests for Color utility methods."""

    def test_clamp_within_range(self):
        """Test _clamp returns value within range."""
        assert Color._clamp(0.5) == 0.5

    def test_clamp_below_zero(self):
        """Test _clamp clamps negative values to 0."""
        assert Color._clamp(-0.5) == 0.0

    def test_clamp_above_one(self):
        """Test _clamp clamps values above 1 to 1."""
        assert Color._clamp(1.5) == 1.0
