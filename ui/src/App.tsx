import { useEffect, useMemo, useState } from "react"
import {
  Bug,
  CheckSquare2,
  Goal,
  Plus,
  Sparkles,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Textarea } from "@/components/ui/textarea"

type ItemType = "Epic" | "Feature" | "Task" | "Bug"
type Item = {
  id: string
  title: string
  type: ItemType
  description: string
  parent_id: string | null
  created_at: string
  updated_at: string
}
type Draft = Pick<Item, "title" | "type" | "description" | "parent_id"> & { id?: string }

const typeMeta = {
  Epic: { icon: Goal, tone: "text-violet-600 bg-violet-500/10 border-violet-500/20" },
  Feature: { icon: Sparkles, tone: "text-blue-600 bg-blue-500/10 border-blue-500/20" },
  Task: { icon: CheckSquare2, tone: "text-emerald-600 bg-emerald-500/10 border-emerald-500/20" },
  Bug: { icon: Bug, tone: "text-rose-600 bg-rose-500/10 border-rose-500/20" },
} as const

const emptyDraft = (parent_id: string | null = null): Draft => ({
  title: "",
  type: "Task",
  description: "",
  parent_id,
})

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const body = await response.json()
  if (!response.ok) throw new Error(body.error || "Something went wrong")
  return body
}

function TypeMark({ type, size = "normal" }: { type: ItemType; size?: "normal" | "small" }) {
  const { icon: Icon, tone } = typeMeta[type]
  return (
    <span className={`inline-flex shrink-0 items-center justify-center rounded ${tone} ${size === "small" ? "size-5" : "size-6"}`}>
      <Icon className={size === "small" ? "size-3" : "size-3.5"} aria-hidden="true" />
      <span className="sr-only">{type}</span>
    </span>
  )
}

function TypeBadge({ type }: { type: ItemType }) {
  return <Badge variant="outline" className={`gap-1 border ${typeMeta[type].tone}`}><TypeMark type={type} size="small" />{type}</Badge>
}

function Tree({ items, parentId, depth, onSelect, onAddChild }: {
  items: Item[]
  parentId: string | null
  depth: number
  onSelect: (item: Item) => void
  onAddChild: (id: string) => void
}) {
  const children = items.filter((item) => item.parent_id === parentId)
  if (!children.length) return null
  return (
    <ul className={depth ? "ml-4 border-l border-border/70 pl-3" : "space-y-1"}>
      {children.map((item) => {
        return (
          <li key={item.id} className="group/list">
            <div className="flex min-w-0 items-center gap-1 rounded-lg pr-1 hover:bg-muted/80">
              <span className="size-6 shrink-0" aria-hidden="true" />
              <button type="button" onClick={() => onSelect(item)} className="flex min-w-0 flex-1 items-center gap-2 rounded-md py-1.5 text-left text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <TypeMark type={item.type} />
                <span className="min-w-0 flex-1 truncate font-medium">{item.title}</span>
                <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">{item.type}</span>
              </button>
              <Button variant="ghost" size="icon-xs" className="invisible shrink-0 group-hover/list:visible" onClick={() => onAddChild(item.id)} aria-label={`Add child to ${item.title}`}>
                <Plus />
              </Button>
            </div>
            <Tree items={items} parentId={item.id} depth={depth + 1} onSelect={onSelect} onAddChild={onAddChild} />
          </li>
        )
      })}
    </ul>
  )
}

function App() {
  const [items, setItems] = useState<Item[]>([])
  const [draft, setDraft] = useState<Draft | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)

  const counts = useMemo(() => Object.fromEntries((Object.keys(typeMeta) as ItemType[]).map((type) => [type, items.filter((item) => item.type === type).length])), [items])
  const blockedParents = useMemo(() => {
    if (!draft?.id) return new Set<string>()
    const blocked = new Set([draft.id])
    const addChildren = (id: string) => items.filter((item) => item.parent_id === id).forEach((item) => { blocked.add(item.id); addChildren(item.id) })
    addChildren(draft.id)
    return blocked
  }, [draft?.id, items])

  const load = async () => {
    setLoading(true)
    try {
      setItems(await request<Item[]>("/api/items"))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load work items")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const openItem = (item: Item) => {
    setError("")
    setExpanded(false)
    setDraft({ ...item })
  }
  const openNew = (parent_id: string | null = null) => {
    setError("")
    setExpanded(false)
    setDraft(emptyDraft(parent_id))
  }
  const save = async () => {
    if (!draft) return
    setError("")
    try {
      const item = await request<Item>(draft.id ? `/api/items/${draft.id}` : "/api/items", {
        method: draft.id ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      })
      await load()
      setDraft(item)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save item")
    }
  }

  return (
    <div className="min-h-svh bg-[#f8f8f8] text-foreground">
      <div className="min-h-svh bg-background">
        <main className="min-w-0">
          <header className="flex h-14 items-center gap-3 border-b px-4 sm:px-6">
            <div className="min-w-0"><h1 className="truncate text-sm font-semibold">Work items</h1><p className="text-[11px] text-muted-foreground">Local-first workspace</p></div>
            <Button onClick={() => openNew()} className="ml-auto gap-1.5"><Plus />New item</Button>
          </header>

          <div className="mx-auto max-w-5xl px-4 py-7 sm:px-8">
              <div className="flex flex-col gap-5 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
                <div><p className="text-sm text-muted-foreground">Plan the work, then open any item to shape the details.</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">All work</h2></div>
                <div className="flex gap-2 overflow-x-auto pb-1">{(Object.keys(typeMeta) as ItemType[]).map((type) => <Badge key={type} variant="outline" className="shrink-0 gap-1.5 py-1"><TypeMark type={type} size="small" />{counts[type]} {type}{counts[type] === 1 ? "" : "s"}</Badge>)}</div>
              </div>

              <section className="mt-5" aria-label="Work item tree">
                {loading ? <p className="py-10 text-sm text-muted-foreground">Loading your workspace…</p> : items.length ? <Tree items={items} parentId={null} depth={0} onSelect={openItem} onAddChild={(id) => openNew(id)} /> : <div className="rounded-xl border border-dashed px-6 py-14 text-center"><span className="mx-auto mb-3 grid size-10 place-items-center rounded-xl bg-muted"><Goal className="size-5 text-muted-foreground" /></span><h3 className="font-semibold">Begin with a work item</h3><p className="mt-1 text-sm text-muted-foreground">Start with an Epic, Feature, Task, or Bug.</p><Button className="mt-4" onClick={() => openNew()}><Plus />Create your first item</Button></div>}
              </section>
          </div>
        </main>
      </div>

      <Sheet open={Boolean(draft)} onOpenChange={(open) => { if (!open) { setDraft(null); setExpanded(false) } }}>
          <SheetContent side="right" className={`flex w-full flex-col gap-0 p-0 sm:max-w-[540px] ${expanded ? "!max-w-none" : ""}`}>
            {draft && <>
              <SheetHeader className="border-b px-5 py-4 text-left">
                <div className="flex items-center gap-2"><TypeMark type={draft.type} /><SheetTitle>{draft.id ? "Edit work item" : "New work item"}</SheetTitle></div>
                <SheetDescription>{draft.id ? "Keep scope and hierarchy clear." : "Capture the smallest useful unit of work."}</SheetDescription>
              </SheetHeader>
              <div className="flex items-center justify-between border-b px-5 py-2">
                <TypeBadge type={draft.type} />
                <Button variant="ghost" size="sm" onClick={() => setExpanded((value) => !value)}>{expanded ? "Return to tree" : "Expand details"}</Button>
              </div>
              <div className="flex-1 overflow-y-auto px-5 py-6">
                <div className="space-y-5">
                  <label className="block text-sm font-medium">Title<Input aria-label="Title" className="mt-2 h-10 text-base" value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="Describe the outcome" autoFocus /></label>
                  <div className="grid gap-5 sm:grid-cols-2">
                    <label className="block text-sm font-medium">Type<Select value={draft.type} onValueChange={(type: ItemType) => setDraft({ ...draft, type })}><SelectTrigger aria-label="Type" className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(typeMeta) as ItemType[]).map((type) => <SelectItem key={type} value={type}><span className="flex items-center gap-2"><TypeMark type={type} size="small" />{type}</span></SelectItem>)}</SelectContent></Select></label>
                    <label className="block text-sm font-medium">Parent<Select value={draft.parent_id || "none"} onValueChange={(parent_id) => setDraft({ ...draft, parent_id: parent_id === "none" ? null : parent_id })}><SelectTrigger aria-label="Parent" className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">No parent</SelectItem>{items.filter((item) => !blockedParents.has(item.id)).map((item) => <SelectItem key={item.id} value={item.id}><span className="flex items-center gap-2"><TypeMark type={item.type} size="small" />{item.title}</span></SelectItem>)}</SelectContent></Select></label>
                  </div>
                  <label className="block text-sm font-medium">Description<Textarea aria-label="Description" className="mt-2 min-h-36" value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="What should happen, and why?" /></label>
                  {error && <p className="rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">{error}</p>}
                </div>
              </div>
              <footer className="flex items-center justify-between border-t px-5 py-4"><Button variant="ghost" onClick={() => openNew(draft.id || null)}><Plus />Add child</Button><div className="flex gap-2"><Button variant="ghost" onClick={() => setDraft(null)}>Cancel</Button><Button onClick={() => void save()}>Save item</Button></div></footer>
            </>}
          </SheetContent>
      </Sheet>
    </div>
  )
}

export default App
