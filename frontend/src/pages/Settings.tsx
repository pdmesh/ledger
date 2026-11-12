import { useState } from "react";
import { Tabs } from "../components/ui";
import DataPrivacy from "./settings/DataPrivacy";
import General from "./settings/General";
import Intelligence from "./settings/Intelligence";
import Merchants from "./settings/Merchants";
import People from "./settings/People";
import Reconciliation from "./settings/Reconciliation";
import Rules from "./settings/Rules";
import Taxonomy from "./settings/Taxonomy";

type Tab = "general" | "people" | "taxonomy" | "merchants" | "rules" | "reconciliation" | "intelligence" | "data";

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("general");
  return (
    <div className="space-y-5">
      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: "general", label: "General" },
          { value: "people", label: "People & identities" },
          { value: "taxonomy", label: "Taxonomy" },
          { value: "merchants", label: "Merchants" },
          { value: "rules", label: "Classification rules" },
          { value: "reconciliation", label: "Reconciliation" },
          { value: "intelligence", label: "Intelligence providers" },
          { value: "data", label: "Privacy & data" },
        ]}
      />
      {tab === "general" && <General />}
      {tab === "people" && <People />}
      {tab === "taxonomy" && <Taxonomy />}
      {tab === "merchants" && <Merchants />}
      {tab === "rules" && <Rules />}
      {tab === "reconciliation" && <Reconciliation />}
      {tab === "intelligence" && <Intelligence />}
      {tab === "data" && <DataPrivacy />}
    </div>
  );
}
