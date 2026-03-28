import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ListEditorProps {
  label: string;
  description?: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder: string;
  minimumRows?: number;
}

export function ListEditor({
  label,
  description,
  values,
  onChange,
  placeholder,
  minimumRows = 1,
}: ListEditorProps) {
  const items = values.length ? values : Array.from({ length: minimumRows }, () => "");

  const updateValue = (index: number, value: string) => {
    const next = [...items];
    next[index] = value;
    onChange(next);
  };

  const addRow = () => onChange([...items, ""]);

  const removeRow = (index: number) => {
    if (items.length <= minimumRows) {
      updateValue(index, "");
      return;
    }
    onChange(items.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <Label>{label}</Label>
          {description ? <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p> : null}
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={addRow}>
          <Plus className="size-4" />
          添加
        </Button>
      </div>
      <div className="space-y-2">
        {items.map((value, index) => (
          <div key={`${label}-${index}`} className="flex items-center gap-2">
            <Input
              value={value}
              placeholder={placeholder}
              onChange={(event) => updateValue(index, event.target.value)}
            />
            <Button type="button" variant="ghost" size="icon" onClick={() => removeRow(index)}>
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
