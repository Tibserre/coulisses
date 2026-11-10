import { AlignLeft, Clock, Cpu, Users } from "lucide-react";
import type { PieceKind } from "../onboarding.ts";

/** What each piece of the chain is said as on screen (ADR 0079): by what it is for, never
 *  by a model's name (P6). Shared by the onboarding and a waiting session. */
export const LABELS: Record<PieceKind, string> = {
  transcribe: "Transcription",
  align: "Alignement des mots",
  diarize: "Qui parle quand",
  tools: "Outils de calcul",
};
export const WHAT: Record<PieceKind, string> = {
  transcribe: "La parole en texte",
  align: "Chaque mot à son instant",
  diarize: "Les voix séparées",
  tools: "Font tourner le tout",
};
export const ICON: Record<PieceKind, typeof AlignLeft> = {
  transcribe: AlignLeft,
  align: Clock,
  diarize: Users,
  tools: Cpu,
};

