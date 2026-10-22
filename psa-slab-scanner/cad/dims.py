"""Shared dimensions (mm). Measure 5 of your own slabs and edit here before printing.

Sources: PSA's published 80.3 x 135.1 x 6.86 mm holder spec, caliper measurements of
80.25 x 135.75 x 6.25 mm, and 2024+ holders with "identical exterior". See docs/RESEARCH.md.
"""

SLAB_W = 80.3  # nominal width
SLAB_H = 135.5  # nominal height
SLAB_T = 6.6  # nominal thickness (old 6.25 .. new 6.86)
SLAB_W_MAX = 82.6
SLAB_H_MAX = 136.5
SLAB_T_MAX = 7.0  # PSA standard; CGC 7.5, BGS/SGC 8.5, PSA thick 10.25
SLAB_MASS_MAX_G = 65.0
LABEL_W, LABEL_H = 70.0, 20.0
LABEL_TOP = 5.0  # label offset from slab top edge (verify on your slabs)
