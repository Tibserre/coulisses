import { Text } from "@astryxdesign/core/Text";
import type { AppInfo } from "../api.ts";

/** Where the data lives and which versions run: always visible (P7). */
export function AppFooter({ info }: { info: AppInfo | null }) {
  if (!info) return null;
  return (
    <footer className="cl-footer">
      <Text type="supporting">
        Données : {info.data_dir} · Coulisses {info.app_version} · moteur {info.engine_version} ·
        chaîne « {info.profile} »
      </Text>
    </footer>
  );
}
