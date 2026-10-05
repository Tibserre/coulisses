import { Switch } from "@astryxdesign/core/Switch";
import { Text } from "@astryxdesign/core/Text";
import type { AppInfo } from "../api.ts";
import { setDevMode, useDevMode } from "../devMode.ts";

/** The developer-mode switch; in that mode, where the data lives and which versions run
 *  (P7). */
export function AppFooter({ info }: { info: AppInfo | null }) {
  const dev = useDevMode();
  return (
    <footer className="cl-footer">
      <Switch label="Mode développeur" value={dev} onChange={setDevMode} />
      {dev && info && (
        <Text type="supporting">
          Données : {info.data_dir} · Coulisses {info.app_version} · moteur{" "}
          {info.engine_version} · chaîne « {info.profile} »
        </Text>
      )}
    </footer>
  );
}
