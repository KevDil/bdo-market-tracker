# Exhaustive EasyOCR Parameter Optimization Results

**Date:** 2025-10-22
**GPU:** NVIDIA GeForce RTX 4070 SUPER
**Total Configurations Tested:** 6240

---

## warehouse_buy

**Total Configs Tested:** 900

### Top 20 Fastest Configurations

| Rank | Time | Canvas | Threshold | Batch | Contrast | Adjust | LowText | Link | Text Preview |
|------|------|--------|-----------|-------|----------|--------|---------|------|-------------|
| 1 | 18.0ms | 400 | 0.65 | 8 | 0.32 | 0.25 | 0.32 | 0.36 | Warehouse Quantity... |
| 2 | 18.2ms | 400 | 0.65 | 8 | 0.28 | 0.30 | 0.32 | 0.36 | Warehouse Quantity... |
| 3 | 18.4ms | 400 | 0.45 | 8 | 0.32 | 0.35 | 0.32 | 0.32 | Warehouse Quantity... |
| 4 | 18.4ms | 400 | 0.70 | 4 | 0.22 | 0.35 | 0.32 | 0.32 | Warehouse Quantity... |
| 5 | 18.4ms | 400 | 0.65 | 8 | 0.26 | 0.30 | 0.36 | 0.36 | Warehouse Quantity... |
| 6 | 18.5ms | 400 | 0.70 | 4 | 0.32 | 0.50 | 0.36 | 0.40 | Warehouse Quantity... |
| 7 | 18.5ms | 400 | 0.45 | 8 | 0.32 | 0.35 | 0.36 | 0.36 | Warehouse Quantity... |
| 8 | 18.5ms | 400 | 0.65 | 8 | 0.26 | 0.50 | 0.32 | 0.32 | Warehouse Quantity... |
| 9 | 18.6ms | 400 | 0.45 | 8 | 0.22 | 0.25 | 0.36 | 0.36 | Warehouse Quantity... |
| 10 | 18.6ms | 400 | 0.65 | 8 | 0.26 | 0.35 | 0.32 | 0.32 | Warehouse Quantity... |
| 11 | 18.7ms | 400 | 0.70 | 4 | 0.28 | 0.30 | 0.36 | 0.36 | Warehouse Quantity... |
| 12 | 18.7ms | 400 | 0.65 | 8 | 0.28 | 0.35 | 0.36 | 0.40 | Warehouse Quantity... |
| 13 | 18.7ms | 400 | 0.65 | 8 | 0.28 | 0.35 | 0.36 | 0.36 | Warehouse Quantity... |
| 14 | 18.8ms | 400 | 0.65 | 8 | 0.32 | 0.50 | 0.36 | 0.36 | Warehouse Quantity... |
| 15 | 18.8ms | 400 | 0.65 | 8 | 0.28 | 0.25 | 0.36 | 0.36 | Warehouse Quantity... |
| 16 | 18.8ms | 400 | 0.65 | 8 | 0.32 | 0.25 | 0.36 | 0.36 | Warehouse Quantity... |
| 17 | 18.8ms | 400 | 0.45 | 8 | 0.22 | 0.25 | 0.36 | 0.40 | Warehouse Quantity... |
| 18 | 18.8ms | 400 | 0.65 | 8 | 0.32 | 0.50 | 0.32 | 0.36 | Warehouse Quantity... |
| 19 | 18.8ms | 400 | 0.70 | 4 | 0.32 | 0.50 | 0.36 | 0.32 | Warehouse Quantity... |
| 20 | 18.8ms | 400 | 0.45 | 8 | 0.32 | 0.40 | 0.36 | 0.40 | Warehouse Quantity... |

### ⭐ Recommended Configuration

```python
# warehouse_buy (Fastest: 18.0ms)
canvas_size = 400
text_threshold = 0.65
batch_size = 8
contrast_ths = 0.32
adjust_contrast = 0.25
low_text = 0.32
link_threshold = 0.36
```

**Extracted Text:** `Warehouse Quantity`

---

## warehouse_sell

**Total Configs Tested:** 900

### Top 20 Fastest Configurations

| Rank | Time | Canvas | Threshold | Batch | Contrast | Adjust | LowText | Link | Text Preview |
|------|------|--------|-----------|-------|----------|--------|---------|------|-------------|
| 1 | 15.9ms | 500 | 0.55 | 4 | 0.22 | 0.40 | 0.40 | 0.32 | In Stock 421... |
| 2 | 15.9ms | 450 | 0.60 | 8 | 0.32 | 0.30 | 0.40 | 0.40 | In Stock 421... |
| 3 | 15.9ms | 500 | 0.55 | 4 | 0.22 | 0.40 | 0.40 | 0.40 | In Stock 421... |
| 4 | 15.9ms | 500 | 0.60 | 6 | 0.28 | 0.30 | 0.36 | 0.40 | In Stock 421... |
| 5 | 15.9ms | 500 | 0.60 | 6 | 0.28 | 0.35 | 0.44 | 0.40 | In Stock 421... |
| 6 | 15.9ms | 500 | 0.60 | 6 | 0.22 | 0.40 | 0.32 | 0.36 | In Stock 421... |
| 7 | 15.9ms | 450 | 0.60 | 8 | 0.32 | 0.30 | 0.44 | 0.40 | In Stock 421... |
| 8 | 15.9ms | 500 | 0.55 | 4 | 0.28 | 0.30 | 0.36 | 0.36 | In Stock 421... |
| 9 | 15.9ms | 500 | 0.60 | 6 | 0.28 | 0.40 | 0.32 | 0.36 | In Stock 421... |
| 10 | 15.9ms | 500 | 0.55 | 4 | 0.26 | 0.30 | 0.44 | 0.36 | In Stock 421... |
| 11 | 15.9ms | 450 | 0.60 | 8 | 0.32 | 0.30 | 0.44 | 0.32 | In Stock 421... |
| 12 | 15.9ms | 500 | 0.60 | 6 | 0.26 | 0.40 | 0.36 | 0.36 | In Stock 421... |
| 13 | 15.9ms | 450 | 0.60 | 8 | 0.28 | 0.25 | 0.44 | 0.36 | In Stock 421... |
| 14 | 15.9ms | 500 | 0.55 | 4 | 0.28 | 0.30 | 0.44 | 0.36 | In Stock 421... |
| 15 | 15.9ms | 500 | 0.55 | 4 | 0.22 | 0.40 | 0.36 | 0.40 | In Stock 421... |
| 16 | 15.9ms | 450 | 0.60 | 8 | 0.28 | 0.30 | 0.40 | 0.36 | In Stock 421... |
| 17 | 15.9ms | 500 | 0.60 | 6 | 0.22 | 0.25 | 0.44 | 0.40 | In Stock 421... |
| 18 | 15.9ms | 450 | 0.60 | 8 | 0.32 | 0.35 | 0.32 | 0.40 | In Stock 421... |
| 19 | 15.9ms | 500 | 0.55 | 4 | 0.28 | 0.30 | 0.40 | 0.32 | In Stock 421... |
| 20 | 15.9ms | 450 | 0.60 | 8 | 0.26 | 0.25 | 0.44 | 0.40 | In Stock 421... |

### ⭐ Recommended Configuration

```python
# warehouse_sell (Fastest: 15.9ms)
canvas_size = 500
text_threshold = 0.55
batch_size = 4
contrast_ths = 0.22
adjust_contrast = 0.4
low_text = 0.4
link_threshold = 0.32
```

**Extracted Text:** `In Stock 421`

---

## balance

**Total Configs Tested:** 900

### Top 20 Fastest Configurations

| Rank | Time | Canvas | Threshold | Batch | Contrast | Adjust | LowText | Link | Text Preview |
|------|------|--------|-----------|-------|----------|--------|---------|------|-------------|
| 1 | 18.1ms | 550 | 0.55 | 8 | 0.22 | 0.35 | 0.32 | 0.36 | Balance 215,072,270,420... |
| 2 | 18.1ms | 400 | 0.70 | 8 | 0.28 | 0.50 | 0.36 | 0.40 | Balance 215,072,270,420... |
| 3 | 18.2ms | 400 | 0.70 | 8 | 0.28 | 0.30 | 0.36 | 0.36 | Balance 215,072,270,420... |
| 4 | 18.2ms | 400 | 0.70 | 8 | 0.22 | 0.35 | 0.36 | 0.40 | Balance 215,072,270,420... |
| 5 | 18.3ms | 400 | 0.70 | 8 | 0.32 | 0.35 | 0.36 | 0.32 | Balance 215,072,270,420... |
| 6 | 18.3ms | 550 | 0.55 | 8 | 0.22 | 0.35 | 0.32 | 0.32 | Balance 215,072,270,420... |
| 7 | 18.3ms | 550 | 0.65 | 2 | 0.32 | 0.30 | 0.36 | 0.40 | Balance 215,072,270,420... |
| 8 | 18.3ms | 550 | 0.55 | 8 | 0.28 | 0.30 | 0.36 | 0.36 | Balance 215,072,270,420... |
| 9 | 18.3ms | 550 | 0.65 | 2 | 0.28 | 0.30 | 0.36 | 0.36 | Balance 215,072,270,420... |
| 10 | 18.3ms | 550 | 0.65 | 2 | 0.32 | 0.25 | 0.36 | 0.40 | Balance 215,072,270,420... |
| 11 | 18.4ms | 550 | 0.55 | 8 | 0.22 | 0.40 | 0.32 | 0.32 | Balance 215,072,270,420... |
| 12 | 18.4ms | 550 | 0.55 | 8 | 0.26 | 0.50 | 0.32 | 0.40 | Balance 215,072,270,420... |
| 13 | 18.4ms | 400 | 0.70 | 8 | 0.22 | 0.25 | 0.36 | 0.36 | Balance 215,072,270,420... |
| 14 | 18.5ms | 400 | 0.70 | 8 | 0.22 | 0.50 | 0.36 | 0.32 | Balance 215,072,270,420... |
| 15 | 18.5ms | 550 | 0.65 | 2 | 0.26 | 0.30 | 0.32 | 0.40 | Balance 215,072,270,420... |
| 16 | 18.5ms | 400 | 0.70 | 8 | 0.26 | 0.40 | 0.32 | 0.32 | Balance 215,072,270,420... |
| 17 | 18.5ms | 550 | 0.55 | 8 | 0.28 | 0.30 | 0.36 | 0.40 | Balance 215,072,270,420... |
| 18 | 18.5ms | 550 | 0.55 | 8 | 0.22 | 0.25 | 0.32 | 0.36 | Balance 215,072,270,420... |
| 19 | 18.6ms | 550 | 0.65 | 2 | 0.28 | 0.30 | 0.36 | 0.36 | Balance 215,072,270,420... |
| 20 | 18.6ms | 400 | 0.70 | 8 | 0.26 | 0.35 | 0.32 | 0.36 | Balance 215,072,270,420... |

### ⭐ Recommended Configuration

```python
# balance (Fastest: 18.1ms)
canvas_size = 550
text_threshold = 0.55
batch_size = 8
contrast_ths = 0.22
adjust_contrast = 0.35
low_text = 0.32
link_threshold = 0.36
```

**Extracted Text:** `Balance 215,072,270,420`

---

## item_name

**Total Configs Tested:** 900

### Top 20 Fastest Configurations

| Rank | Time | Canvas | Threshold | Batch | Contrast | Adjust | LowText | Link | Text Preview |
|------|------|--------|-----------|-------|----------|--------|---------|------|-------------|
| 1 | 20.2ms | 550 | 0.60 | 6 | 0.32 | 0.30 | 0.32 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 2 | 20.3ms | 550 | 0.50 | 4 | 0.26 | 0.30 | 0.32 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 3 | 20.4ms | 550 | 0.60 | 6 | 0.32 | 0.50 | 0.32 | 0.40 | 2025.10.21.21.07 Unknown Seed... |
| 4 | 20.4ms | 550 | 0.50 | 4 | 0.26 | 0.30 | 0.36 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 5 | 20.5ms | 600 | 0.50 | 3 | 0.28 | 0.30 | 0.36 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 6 | 20.5ms | 550 | 0.50 | 4 | 0.28 | 0.30 | 0.36 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 7 | 20.6ms | 600 | 0.50 | 3 | 0.28 | 0.35 | 0.32 | 0.32 | 2025.10.21.21.07 Unknown Seed... |
| 8 | 20.6ms | 550 | 0.50 | 4 | 0.26 | 0.30 | 0.32 | 0.40 | 2025.10.21.21.07 Unknown Seed... |
| 9 | 20.6ms | 550 | 0.50 | 4 | 0.22 | 0.50 | 0.32 | 0.40 | 2025.10.21.21.07 Unknown Seed... |
| 10 | 20.6ms | 550 | 0.50 | 4 | 0.28 | 0.50 | 0.36 | 0.40 | 2025.10.21.21.07 Unknown Seed... |
| 11 | 20.7ms | 550 | 0.60 | 6 | 0.28 | 0.30 | 0.36 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 12 | 20.8ms | 550 | 0.50 | 4 | 0.26 | 0.30 | 0.36 | 0.40 | 2025.10.21.21.07 Unknown Seed... |
| 13 | 20.8ms | 550 | 0.60 | 6 | 0.32 | 0.50 | 0.36 | 0.32 | 2025.10.21.21.07 Unknown Seed... |
| 14 | 20.8ms | 600 | 0.50 | 2 | 0.28 | 0.30 | 0.36 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 15 | 20.8ms | 600 | 0.50 | 3 | 0.22 | 0.30 | 0.36 | 0.32 | 2025.10.21.21.07 Unknown Seed... |
| 16 | 20.9ms | 550 | 0.60 | 4 | 0.28 | 0.30 | 0.36 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 17 | 20.9ms | 550 | 0.50 | 4 | 0.26 | 0.30 | 0.32 | 0.32 | 2025.10.21.21.07 Unknown Seed... |
| 18 | 21.0ms | 600 | 0.50 | 3 | 0.32 | 0.40 | 0.32 | 0.36 | 2025.10.21.21.07 Unknown Seed... |
| 19 | 21.0ms | 550 | 0.50 | 4 | 0.32 | 0.40 | 0.32 | 0.32 | 2025.10.21.21.07 Unknown Seed... |
| 20 | 21.1ms | 700 | 0.50 | 8 | 0.28 | 0.30 | 0.36 | 0.36 | 2025.10.21.21.07 Unknown Seed... |

### ⭐ Recommended Configuration

```python
# item_name (Fastest: 20.2ms)
canvas_size = 550
text_threshold = 0.6
batch_size = 6
contrast_ths = 0.32
adjust_contrast = 0.3
low_text = 0.32
link_threshold = 0.36
```

**Extracted Text:** `2025.10.21.21.07 Unknown Seed`

---

## label

**Total Configs Tested:** 900

### Top 20 Fastest Configurations

| Rank | Time | Canvas | Threshold | Batch | Contrast | Adjust | LowText | Link | Text Preview |
|------|------|--------|-----------|-------|----------|--------|---------|------|-------------|
| 1 | 56.5ms | 1000 | 0.70 | 8 | 0.28 | 0.25 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 2 | 57.3ms | 1000 | 0.70 | 8 | 0.32 | 0.35 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 3 | 57.9ms | 1000 | 0.70 | 8 | 0.28 | 0.30 | 0.40 | 0.40 | Items Listed 900 Sales Completed 200 Fra... |
| 4 | 58.0ms | 1000 | 0.70 | 8 | 0.26 | 0.40 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 5 | 58.1ms | 1000 | 0.70 | 8 | 0.26 | 0.35 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 6 | 58.3ms | 800 | 0.55 | 8 | 0.26 | 0.30 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 7 | 58.4ms | 800 | 0.55 | 8 | 0.28 | 0.40 | 0.40 | 0.40 | Items Listed 900 Sales Completed 200 Fra... |
| 8 | 58.4ms | 800 | 0.55 | 8 | 0.22 | 0.50 | 0.40 | 0.40 | Items Listed 900 Sales Completed 200 Fra... |
| 9 | 58.6ms | 1000 | 0.60 | 8 | 0.22 | 0.25 | 0.40 | 0.36 | Items Listed 900 Sales Completed 200 Fra... |
| 10 | 58.7ms | 1000 | 0.70 | 8 | 0.28 | 0.50 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 11 | 58.9ms | 1000 | 0.60 | 8 | 0.28 | 0.30 | 0.40 | 0.40 | Items Listed 900 Sales Completed 200 Fra... |
| 12 | 59.0ms | 1000 | 0.60 | 8 | 0.22 | 0.40 | 0.40 | 0.40 | Items Listed 900 Sales Completed 200 Fra... |
| 13 | 59.2ms | 1000 | 0.60 | 8 | 0.32 | 0.25 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 14 | 59.2ms | 1000 | 0.60 | 8 | 0.32 | 0.50 | 0.40 | 0.36 | Items Listed 900 Sales Completed 200 Fra... |
| 15 | 59.3ms | 1000 | 0.60 | 8 | 0.28 | 0.50 | 0.40 | 0.36 | Items Listed 900 Sales Completed 200 Fra... |
| 16 | 59.3ms | 1000 | 0.60 | 8 | 0.22 | 0.35 | 0.40 | 0.36 | Items Listed 900 Sales Completed 200 Fra... |
| 17 | 59.3ms | 800 | 0.55 | 8 | 0.22 | 0.40 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 18 | 59.3ms | 1000 | 0.60 | 8 | 0.28 | 0.50 | 0.40 | 0.40 | Items Listed 900 Sales Completed 200 Fra... |
| 19 | 59.4ms | 800 | 0.55 | 8 | 0.32 | 0.50 | 0.40 | 0.32 | 200 Items Listed 900 Sales Completed Fra... |
| 20 | 59.5ms | 1000 | 0.60 | 8 | 0.26 | 0.25 | 0.40 | 0.40 | Items Listed 900 Sales Completed 200 Fra... |

### ⭐ Recommended Configuration

```python
# label (Fastest: 56.5ms)
canvas_size = 1000
text_threshold = 0.7
batch_size = 8
contrast_ths = 0.28
adjust_contrast = 0.25
low_text = 0.4
link_threshold = 0.32
```

**Extracted Text:** `200 Items Listed 900 Sales Completed Fragment of the Deep Sea Completed Registration Count Sales Embers of Despair 10 / Sales Completed Registration Count Dehkia's Artifact AlI Damage Reduction Redistration Count Sales Completed`

---

## log

**Total Configs Tested:** 870

### Top 20 Fastest Configurations

| Rank | Time | Canvas | Threshold | Batch | Contrast | Adjust | LowText | Link | Text Preview |
|------|------|--------|-----------|-------|----------|--------|---------|------|-------------|
| 1 | 151.3ms | 1200 | 0.55 | 8 | 0.22 | 0.35 | 0.36 | 0.36 | All Damage Reduction xl for 7,550,000,00... |
| 2 | 151.4ms | 1000 | 0.45 | 8 | 0.22 | 0.35 | 0.36 | 0.40 | All Damage Reduction xl for 7,550,000,00... |
| 3 | 151.6ms | 1200 | 0.55 | 8 | 0.22 | 0.50 | 0.36 | 0.40 | All Damage Reduction xl for 7,550,000,00... |
| 4 | 152.3ms | 1000 | 0.70 | 8 | 0.26 | 0.50 | 0.36 | 0.36 | All Damage Reduction xl for 7,550,000,00... |
| 5 | 152.9ms | 1000 | 0.70 | 8 | 0.26 | 0.30 | 0.36 | 0.36 | All Damage Reduction xl for 7,550,000,00... |
| 6 | 153.7ms | 1000 | 0.70 | 8 | 0.22 | 0.30 | 0.36 | 0.40 | All Damage Reduction xl for 7,550,000,00... |
| 7 | 154.1ms | 1000 | 0.70 | 8 | 0.26 | 0.40 | 0.36 | 0.36 | All Damage Reduction xl for 7,550,000,00... |
| 8 | 154.4ms | 1000 | 0.70 | 8 | 0.26 | 0.30 | 0.36 | 0.32 | All Damage Reduction xl for 7,550,000,00... |
| 9 | 155.1ms | 1000 | 0.45 | 8 | 0.22 | 0.25 | 0.36 | 0.36 | All Damage Reduction xl for 7,550,000,00... |
| 10 | 155.2ms | 1000 | 0.70 | 8 | 0.26 | 0.40 | 0.36 | 0.40 | All Damage Reduction xl for 7,550,000,00... |
| 11 | 155.6ms | 1000 | 0.70 | 8 | 0.22 | 0.25 | 0.36 | 0.40 | All Damage Reduction xl for 7,550,000,00... |
| 12 | 155.6ms | 1000 | 0.70 | 8 | 0.26 | 0.30 | 0.36 | 0.40 | All Damage Reduction xl for 7,550,000,00... |
| 13 | 155.7ms | 1000 | 0.70 | 8 | 0.22 | 0.30 | 0.36 | 0.32 | All Damage Reduction xl for 7,550,000,00... |
| 14 | 155.7ms | 1000 | 0.45 | 8 | 0.22 | 0.25 | 0.36 | 0.32 | All Damage Reduction xl for 7,550,000,00... |
| 15 | 156.4ms | 1000 | 0.70 | 8 | 0.22 | 0.50 | 0.36 | 0.36 | All Damage Reduction xl for 7,550,000,00... |
| 16 | 156.4ms | 1000 | 0.45 | 8 | 0.22 | 0.40 | 0.36 | 0.32 | All Damage Reduction xl for 7,550,000,00... |
| 17 | 156.9ms | 1000 | 0.45 | 8 | 0.22 | 0.40 | 0.36 | 0.40 | All Damage Reduction xl for 7,550,000,00... |
| 18 | 157.0ms | 1000 | 0.70 | 8 | 0.26 | 0.50 | 0.36 | 0.32 | All Damage Reduction xl for 7,550,000,00... |
| 19 | 157.3ms | 1000 | 0.45 | 8 | 0.22 | 0.35 | 0.36 | 0.36 | All Damage Reduction xl for 7,550,000,00... |
| 20 | 157.5ms | 1000 | 0.70 | 8 | 0.26 | 0.25 | 0.36 | 0.40 | All Damage Reduction xl for 7,550,000,00... |

### ⭐ Recommended Configuration

```python
# log (Fastest: 151.3ms)
canvas_size = 1200
text_threshold = 0.55
batch_size = 8
contrast_ths = 0.22
adjust_contrast = 0.35
low_text = 0.36
link_threshold = 0.36
```

**Extracted Text:** `All Damage Reduction xl for 7,550,000,000 Silver. T= 2025.10.21 23.18 Listed Dehkia'$ Artifact All Damage Reduction xl from market listing 2025.10.21 23.18 Withdrew Dehkia's Artifact encompl_ Placed order of Dehkia'$ Fragment x5 for 282,500,000 Silver 2025.10.21 23.18 Transaction of Dehkia's Fragment xl worth 55,000,000 Silver has 2025.10.21 23.18 1 31.5% been 33b4Bi 0 / 35 Sell Buy Enter search term:`

---

## metrics

**Total Configs Tested:** 870

### Top 20 Fastest Configurations

| Rank | Time | Canvas | Threshold | Batch | Contrast | Adjust | LowText | Link | Text Preview |
|------|------|--------|-----------|-------|----------|--------|---------|------|-------------|
| 1 | 186.0ms | 600 | 0.50 | 8 | 0.28 | 0.35 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 2 | 186.1ms | 600 | 0.55 | 8 | 0.32 | 0.30 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 3 | 187.4ms | 600 | 0.55 | 8 | 0.26 | 0.35 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 4 | 187.9ms | 600 | 0.50 | 8 | 0.28 | 0.25 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 5 | 188.8ms | 600 | 0.65 | 8 | 0.28 | 0.30 | 0.36 | 0.36 | Collect AlI Listed   900 Sales Completed... |
| 6 | 188.9ms | 600 | 0.50 | 8 | 0.26 | 0.30 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 7 | 189.2ms | 600 | 0.55 | 8 | 0.32 | 0.40 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 8 | 189.5ms | 600 | 0.65 | 8 | 0.22 | 0.25 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 9 | 189.5ms | 600 | 0.65 | 8 | 0.32 | 0.50 | 0.36 | 0.40 | Collect AlI Listed   900 Sales Completed... |
| 10 | 189.6ms | 600 | 0.65 | 8 | 0.22 | 0.40 | 0.36 | 0.36 | Collect AlI Listed   900 Sales Completed... |
| 11 | 190.1ms | 600 | 0.50 | 8 | 0.28 | 0.50 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 12 | 190.2ms | 600 | 0.55 | 8 | 0.22 | 0.25 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 13 | 190.5ms | 600 | 0.50 | 8 | 0.22 | 0.25 | 0.36 | 0.40 | Collect AlI Listed   900 Sales Completed... |
| 14 | 190.6ms | 600 | 0.50 | 8 | 0.32 | 0.25 | 0.36 | 0.40 | Collect AlI Listed   900 Sales Completed... |
| 15 | 191.5ms | 600 | 0.55 | 8 | 0.22 | 0.35 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 16 | 191.5ms | 600 | 0.65 | 8 | 0.22 | 0.35 | 0.36 | 0.36 | Collect AlI Listed   900 Sales Completed... |
| 17 | 191.8ms | 600 | 0.65 | 8 | 0.32 | 0.25 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 18 | 191.9ms | 600 | 0.50 | 8 | 0.28 | 0.40 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 19 | 191.9ms | 600 | 0.65 | 8 | 0.26 | 0.50 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |
| 20 | 192.0ms | 600 | 0.55 | 8 | 0.32 | 0.25 | 0.36 | 0.32 | Collect AlI Listed   900 Sales Completed... |

### ⭐ Recommended Configuration

```python
# metrics (Fastest: 186.0ms)
canvas_size = 600
text_threshold = 0.5
batch_size = 8
contrast_ths = 0.28
adjust_contrast = 0.35
low_text = 0.36
link_threshold = 0.32
```

**Extracted Text:** `Collect AlI Listed   900 Sales Completed   200 Items 2025 08-25 18.46 8 Cancel Fragment of the Deep Sea 225,000 Registration Count 6 / Sales Completed Re-list 2025 1C-19 21.06 Cancel Embers of Despair 9,000,000 Registration Count 10 / Sales Completed : 0 Re-list Dehkia'$ Artifact - 2025 10-21 23.18 Cancel AlI Damage Reduction 7,550,000,000 Registration Count 1 / Sales Completed Re-list 2025 09-06 14.26 8 Cancel Mysterious Powder 1,250 Registration Count Sales Completed 300 Re-list Reforge Stone 2025 07-21 20.09 8 Cancel All Accuracy 125,000,000 Registration Count 2 / Sales Completed Re-list 2025 07-21 20.10 € Cancel Down Attack Damage Reforge Stone Registration Count 2 / Sales Completed : 125,000,000 Re-list`

---

