"use client";
import * as React from "react"
import { Check, ChevronsUpDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

interface TeamSelectProps {
  value: string;
  onValueChange: (value: string) => void;
  teams: string[];
  placeholder?: string;
}

export function TeamSelect({ value, onValueChange, teams, placeholder = "Selecione..." }: TeamSelectProps) {
  const [open, setOpen] = React.useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between h-10 font-normal"
        >
          {value ? value : <span className="text-muted-foreground">{placeholder}</span>}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[300px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Buscar equipe..." className="h-9" />
          <CommandList>
            <CommandEmpty>Nenhuma equipe encontrada.</CommandEmpty>
            <CommandGroup>
              {teams.map((team) => (
                <CommandItem
                  key={team}
                  value={team}
                  onSelect={(currentValue) => {
                    // Shadcn Command lowercases the value on select sometimes, so we find the real team name.
                    // We use `team` directly since we bind it correctly.
                    onValueChange(team === value ? "" : team)
                    setOpen(false)
                  }}
                >
                  {team}
                  <Check
                    className={cn(
                      "ml-auto h-4 w-4",
                      value === team ? "opacity-100" : "opacity-0"
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
