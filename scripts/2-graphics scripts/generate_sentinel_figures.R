#!/usr/bin/env Rscript

# Genera las figuras Sentinel-2 del manuscrito:
#   Figure5.png tendencias mensuales de NDVI, EVI y LSWI
#   Figure6.png medias marginales, IC 95 % y letras de significancia

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(lubridate)
  library(ggplot2)
  library(patchwork)
  library(stringr)
  library(scales)
})

# El script vive en scripts/2-graphics scripts/, dos niveles bajo la raiz del
# proyecto (Analisis/); por eso se sube tres niveles desde la ruta del script
# (archivo -> "2-graphics scripts" -> "scripts" -> raiz) para ubicar data/ y
# figures/ de forma robusta sin importar desde donde se invoque Rscript.
project_root <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) == 1) {
    script_path <- normalizePath(sub("^--file=", "", file_arg))
    return(dirname(dirname(dirname(script_path))))
  }
  wd <- normalizePath(getwd())
  if (basename(dirname(wd)) == "scripts") return(dirname(dirname(wd)))
  if (basename(wd) == "scripts") return(dirname(wd))
  wd
}

root_dir <- project_root()
source(file.path(root_dir, "scripts", "2-graphics scripts", "figure_style.R"))
input_file <- file.path(root_dir, "data", "datos_trapiche_sentinel.csv")
output_dir <- file.path(root_dir, "figures")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

# Meses utilizados para definir la época húmeda en Figure6_b.
WET_MONTHS <- c(10, 11, 12, 1, 2, 3, 4)

raw_data <- read_csv(input_file, show_col_types = FALSE) %>%
  mutate(
    DateR = as.Date(Date),
    Snow = as.numeric(Snow),
    across(c(NDVI, EVI, LSWI), as.numeric),
    across(c(NDVI, EVI, LSWI), ~ if_else(between(.x, -1, 1), .x, NA_real_))
  )

# -----------------------------------------------------------------------------
# Figura 5: tendencias mensuales observadas
# -----------------------------------------------------------------------------

monthly_by_sector <- raw_data %>%
  filter(
    !is.na(DateR), DateR >= as.Date("2020-01-01"),
    DateR <= as.Date("2026-12-31"), Snow == 0
  ) %>%
  mutate(Month = floor_date(DateR, unit = "month")) %>%
  group_by(Month, tratamiento) %>%
  summarise(across(c(NDVI, EVI, LSWI), ~ mean(.x, na.rm = TRUE)), .groups = "drop")

make_figure5 <- function(separate_controls = FALSE) {
  if (separate_controls) {
    monthly_treatments <- monthly_by_sector %>%
      mutate(Tratamiento = unname(TREATMENT_LABELS[as.character(tratamiento)]))
    treatment_levels <- c("Control 1", "Control 2", "Restaurado", "No restaurado")
    treatment_colors <- TREATMENT_COLORS
  } else {
    controls <- monthly_by_sector %>%
      filter(tratamiento %in% c("control 1", "control 2")) %>%
      group_by(Month) %>%
      summarise(across(c(NDVI, EVI, LSWI), ~ mean(.x, na.rm = TRUE)), .groups = "drop") %>%
      mutate(Tratamiento = "Control")

    restored <- monthly_by_sector %>%
      filter(tratamiento == "sector restaurado") %>%
      mutate(Tratamiento = "Restaurado")

    unrestored <- monthly_by_sector %>%
      filter(tratamiento == "sector no restaurado") %>%
      mutate(Tratamiento = "No restaurado")

    monthly_treatments <- bind_rows(controls, restored, unrestored)
    treatment_levels <- c("Control", "Restaurado", "No restaurado")
    treatment_colors <- AGGREGATED_TREATMENT_COLORS
  }

  monthly_long <- monthly_treatments %>%
    select(Month, Tratamiento, NDVI, EVI, LSWI) %>%
    pivot_longer(c(NDVI, EVI, LSWI), names_to = "Indice", values_to = "Valor") %>%
    filter(!is.na(Valor)) %>%
    filter(!(Indice == "LSWI" & Tratamiento == "No restaurado" &
               Month == as.Date("2021-09-01"))) %>%
    mutate(
      Tratamiento = factor(Tratamiento, levels = treatment_levels),
      Indice = factor(Indice, levels = c("NDVI", "EVI", "LSWI"),
                      labels = c("a) NDVI", "b) EVI", "c) LSWI"))
    )

  ggplot(
    monthly_long,
    aes(Month, Valor, color = Tratamiento, group = Tratamiento)
  ) +
    geom_line(linewidth = 0.9, alpha = 0.9) +
    geom_point(size = 1.2, alpha = 0.8) +
    facet_wrap(~Indice, ncol = 1, scales = "free_y") +
    scale_x_date(date_breaks = "1 year", date_minor_breaks = "3 months",
                 date_labels = "%Y", expand = expansion(mult = c(0.01, 0.02))) +
    scale_y_continuous(labels = label_number(accuracy = 0.01)) +
    scale_color_manual(values = treatment_colors, drop = FALSE) +
    labs(
      title = NULL,
      x = "Fecha", y = "Media mensual", color = "Tratamiento"
    ) +
    manuscript_theme() +
    theme(
      strip.background = element_rect(fill = "grey95", color = "grey70"),
      strip.text = element_text(face = "bold", size = 14, hjust = 0),
      panel.grid.major = element_line(color = "grey90", linewidth = 0.3)
    )
}

figure5 <- make_figure5(separate_controls = FALSE)
figure5_separate <- make_figure5(separate_controls = TRUE)

ggsave(file.path(output_dir, "Figure5.png"), figure5,
       width = FIGURE_WIDTH, height = 7, dpi = 320, bg = "white")
ggsave(file.path(output_dir, "Figure5_controles_separados.png"), figure5_separate,
       width = FIGURE_WIDTH, height = 7, dpi = 320, bg = "white")

# -----------------------------------------------------------------------------
# Figura 6: resultados del modelo mixto (emmeans, IC 95 % y CLD)
# -----------------------------------------------------------------------------
# Los valores coinciden con la tabla del manuscrito y provienen del flujo de
# modelos mixtos de Analisis Sentinel 2.R.

emmeans_data <- tribble(
  ~Indice, ~Epoca, ~tratamiento, ~emmean, ~lower.CL, ~upper.CL, ~group,
  "NDVI", "Húmeda", "control 1", 0.537, 0.521, 0.553, "d",
  "NDVI", "Húmeda", "control 2", 0.365, 0.350, 0.381, "b",
  "NDVI", "Húmeda", "sector no restaurado", 0.272, 0.256, 0.288, "a",
  "NDVI", "Húmeda", "sector restaurado", 0.465, 0.450, 0.481, "c",
  "NDVI", "Seca", "control 1", 0.273, 0.256, 0.291, "c",
  "NDVI", "Seca", "control 2", 0.200, 0.182, 0.218, "b",
  "NDVI", "Seca", "sector no restaurado", 0.240, 0.223, 0.258, "a",
  "NDVI", "Seca", "sector restaurado", 0.244, 0.226, 0.261, "a",
  "EVI", "Húmeda", "control 1", 0.398, 0.386, 0.410, "d",
  "EVI", "Húmeda", "control 2", 0.280, 0.268, 0.291, "b",
  "EVI", "Húmeda", "sector no restaurado", 0.124, 0.112, 0.135, "a",
  "EVI", "Húmeda", "sector restaurado", 0.315, 0.304, 0.327, "c",
  "EVI", "Seca", "control 1", 0.184, 0.171, 0.197, "a",
  "EVI", "Seca", "control 2", 0.144, 0.131, 0.157, "c",
  "EVI", "Seca", "sector no restaurado", 0.109, 0.096, 0.122, "b",
  "EVI", "Seca", "sector restaurado", 0.169, 0.156, 0.182, "a"
) %>%
  mutate(
    tratamiento = standardize_treatment(tratamiento),
    Epoca = factor(Epoca, levels = c("Húmeda", "Seca"))
  )

season_background <- tibble(
  Epoca = factor(c("Húmeda", "Seca"), levels = c("Húmeda", "Seca")),
  fill = c("#6AA84F", "#FFD966")
)

boxplot_data <- raw_data %>%
  filter(!is.na(DateR), Snow == 0, !is.na(tratamiento)) %>%
  mutate(
    Epoca = factor(
      if_else(month(DateR) %in% WET_MONTHS, "Húmeda", "Seca"),
      levels = c("Húmeda", "Seca")
    ),
    tratamiento = standardize_treatment(tratamiento)
  ) %>%
  pivot_longer(
    cols = c(NDVI, EVI), names_to = "Indice", values_to = "Valor"
  ) %>%
  filter(!is.na(Valor))

make_emmeans_plot <- function(index_name) {
  index_data <- filter(emmeans_data, Indice == index_name)
  ggplot(index_data, aes(tratamiento, emmean, color = tratamiento)) +
    geom_rect(
      data = season_background, inherit.aes = FALSE,
      aes(xmin = -Inf, xmax = Inf, ymin = -Inf, ymax = Inf, fill = fill),
      alpha = 0.12, color = NA
    ) +
    geom_errorbar(aes(ymin = lower.CL, ymax = upper.CL),
                  width = 0.12, linewidth = 0.9) +
    geom_point(size = 2.8) +
    geom_text(aes(y = upper.CL, label = group),
              vjust = -0.8, size = 5, fontface = "bold", show.legend = FALSE) +
    facet_wrap(~Epoca, nrow = 1) +
    scale_color_manual(values = TREATMENT_COLORS, drop = FALSE) +
    scale_fill_identity(guide = "none") +
    scale_y_continuous(expand = expansion(mult = c(0.06, 0.16))) +
    labs(
      x = "Tratamiento",
      y = paste(index_name, "medio estimado (emmeans, IC 95 %)")
    ) +
    manuscript_theme() +
    theme(
      strip.background = element_rect(fill = "grey96", color = "grey30"),
      axis.text.x = element_text(size = 12, angle = 45, hjust = 1),
      legend.position = "top"
    )
}

make_boxplot <- function(index_name) {
  index_data <- filter(boxplot_data, Indice == index_name)
  letters_data <- emmeans_data %>%
    filter(Indice == index_name) %>%
    select(Epoca, tratamiento, group) %>%
    left_join(
      index_data %>%
        group_by(Epoca, tratamiento) %>%
        summarise(y = max(Valor, na.rm = TRUE), .groups = "drop"),
      by = c("Epoca", "tratamiento")
    ) %>%
    group_by(Epoca) %>%
    mutate(y = y + 0.08 * diff(range(y, na.rm = TRUE))) %>%
    ungroup()

  ggplot(index_data, aes(tratamiento, Valor, color = tratamiento, fill = tratamiento)) +
    geom_rect(
      data = season_background, inherit.aes = FALSE,
      aes(xmin = -Inf, xmax = Inf, ymin = -Inf, ymax = Inf, fill = fill),
      alpha = 0.12, color = NA
    ) +
    geom_boxplot(width = 0.62, alpha = 0.22, outlier.shape = NA,
                 linewidth = 0.7) +
    geom_jitter(width = 0.10, alpha = 0.10, size = 0.55, show.legend = FALSE) +
    geom_text(
      data = letters_data,
      aes(x = tratamiento, y = y, label = group, color = tratamiento),
      inherit.aes = FALSE, size = 5, fontface = "bold", show.legend = FALSE
    ) +
    facet_wrap(~Epoca, nrow = 1) +
    scale_color_manual(values = TREATMENT_COLORS, drop = FALSE) +
    scale_fill_manual(
      values = c(TREATMENT_COLORS,
                 setNames(season_background$fill, season_background$fill)),
      breaks = names(TREATMENT_COLORS), drop = FALSE, guide = "none"
    ) +
    scale_y_continuous(expand = expansion(mult = c(0.04, 0.14))) +
    labs(
      x = "Tratamiento", y = paste(index_name, "observado"),
      color = "Tratamiento", fill = "Tratamiento"
    ) +
    manuscript_theme() +
    theme(
      strip.background = element_rect(fill = "grey96", color = "grey30"),
      axis.text.x = element_text(size = 12, angle = 45, hjust = 1),
      legend.position = "top"
    )
}

add_figure6_annotation <- function(plot) {
  plot +
  plot_layout(guides = "collect") +
  plot_annotation(
    tag_levels = "a",
    tag_suffix = ")"
  ) &
  theme(
    legend.position = "top",
    plot.tag = element_text(size = 16, face = "bold", family = "serif")
  )
}

figure6_a <- add_figure6_annotation(
  make_emmeans_plot("NDVI") / make_emmeans_plot("EVI")
)

figure6_b <- add_figure6_annotation(
  make_boxplot("NDVI") / make_boxplot("EVI")
)

ggsave(file.path(output_dir, "Figure6_a.png"), figure6_a,
       width = FIGURE_WIDTH, height = 7.4, dpi = 320, bg = "white")

ggsave(file.path(output_dir, "Figure6_b.png"), figure6_b,
       width = FIGURE_WIDTH, height = 7.4, dpi = 320, bg = "white")

message("Creadas: Figure5.png, Figure5_controles_separados.png, Figure6_a.png y Figure6_b.png")
