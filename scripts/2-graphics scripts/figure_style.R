# Estilo gráfico común para todas las figuras analíticas del manuscrito.
# Este archivo centraliza nombres, colores y tamaños para evitar diferencias
# accidentales entre scripts.

FIGURE_WIDTH <- 7

TREATMENT_LABELS <- c(
  "control 1" = "Control 1",
  "control 2" = "Control 2",
  "sector no restaurado" = "No restaurado",
  "sector restaurado" = "Restaurado"
)

TREATMENT_LEVELS <- unname(TREATMENT_LABELS)

TREATMENT_COLORS <- c(
  "Control 1" = "#1B4D3E",
  "Control 2" = "#4D8659",
  "No restaurado" = "#A62C2C",
  "Restaurado" = "#D4A574"
)

AGGREGATED_TREATMENT_COLORS <- c(
  "Control" = "#1B4D3E",
  "No restaurado" = "#A62C2C",
  "Restaurado" = "#D4A574"
)

standardize_treatment <- function(values) {
  labels <- unname(TREATMENT_LABELS[as.character(values)])
  factor(labels, levels = TREATMENT_LEVELS)
}

manuscript_theme <- function() {
  theme_classic(base_size = 13, base_family = "serif") +
    theme(
      plot.title = element_text(face = "bold", size = 15, hjust = 0.5, margin = margin(t = 3, b = 9)),
      plot.tag = element_text(face = "bold", size = 18, family = "serif"),
      axis.title = element_text(size = 14, color = "black"),
      axis.text = element_text(size = 14.5, color = "black"),
      legend.title = element_text(face = "bold", size = 12),
      legend.text = element_text(size = 11.5),
      legend.margin = margin(t = 0, b = 4),
      legend.box.spacing = unit(0.2, "cm"),
      strip.text = element_text(face = "bold", size = 14),
      legend.position = "top"
    )
}