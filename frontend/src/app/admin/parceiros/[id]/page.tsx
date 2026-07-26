"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Loader2, X } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { adminApi } from "@/lib/adminApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente", active: "Ativo", paused: "Pausado", rejected: "Rejeitado",
};

function fmt(d: string) { return new Date(d).toLocaleString("pt-BR"); }

function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-2xl border border-border bg-card shadow-2xl p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold">{title}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Label className="text-xs text-muted-foreground mb-1 block">{label}</Label>
      {children}
    </div>
  );
}

type EditForm = {
  name: string; code: string; commission_pct: string; commission_fixed_brl: string;
  status: string; contact_email: string; contact_phone: string; cpf: string;
  payment_type: string; discount_pcts: string; notes: string;
};

export default function PartnerDetailPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const id = String(params.id);
  const isAdmin = user && (user.role === "owner" || user.role === "manager" || user.email === "valerioeducfin@gmail.com");

  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [form, setForm] = useState<EditForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => { if (!loading && !isAdmin) router.replace("/"); }, [loading, isAdmin, router]);

  const load = useCallback(async () => {
    try { setDetail(await adminApi.affiliateDetail(id)); } catch (e) { setErr((e as Error).message); }
  }, [id]);

  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);

  if (!isAdmin || !detail) {
    return (
      <div className="flex justify-center py-20">
        {err ? <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-4">{err}</div> : <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />}
      </div>
    );
  }

  const payments = (detail.payments as Record<string, unknown>[]) || [];
  const demoLogs = (detail.demo_access_logs as Record<string, unknown>[]) || [];
  const referredPartners = (detail.referred_partners as Record<string, unknown>[]) || [];

  function openEdit() {
    setSaveErr(null);
    setForm({
      name: String(detail!.name ?? ""), code: String(detail!.code ?? ""),
      commission_pct: detail!.commission_pct != null ? String(detail!.commission_pct) : "",
      commission_fixed_brl: detail!.commission_fixed_brl != null ? String(detail!.commission_fixed_brl) : "",
      status: String(detail!.status ?? "active"),
      contact_email: String(detail!.contact_email ?? ""), contact_phone: String(detail!.contact_phone ?? ""),
      cpf: String(detail!.cpf ?? ""), payment_type: String(detail!.payment_type ?? ""),
      discount_pcts: detail!.discount_pcts != null ? String(detail!.discount_pcts) : "",
      notes: String(detail!.notes ?? ""),
    });
    setEditOpen(true);
  }

  async function submitEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    setSaveErr(null);
    try {
      await adminApi.patchAffiliate(id, {
        name: form.name, code: form.code,
        commission_pct: form.commission_pct === "" ? null : form.commission_pct,
        commission_fixed_brl: form.commission_fixed_brl === "" ? null : form.commission_fixed_brl,
        status: form.status,
        contact_email: form.contact_email || null, contact_phone: form.contact_phone || null,
        cpf: form.cpf || null, payment_type: form.payment_type || null,
        discount_pcts: form.discount_pcts === "" ? null : form.discount_pcts,
        notes: form.notes || null,
      });
      setEditOpen(false);
      await load();
    } catch (e) {
      setSaveErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function confirmDeletePartner() {
    setDeleting(true);
    try {
      await adminApi.deleteAffiliate(id);
      router.replace("/admin");
    } catch (e) {
      setDeleting(false);
      setConfirmDelete(false);
      setErr((e as Error).message);
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/admin"><ArrowLeft className="w-4 h-4 text-muted-foreground hover:text-foreground" /></Link>
        <h1 className="text-2xl font-bold flex-1">{String(detail.name)}</h1>
        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
          {STATUS_LABEL[String(detail.status)] ?? String(detail.status)}
        </span>
        <Button size="sm" variant="outline" onClick={openEdit}>Editar</Button>
        <Button size="sm" variant="destructive" onClick={() => setConfirmDelete(true)}>Excluir</Button>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-lg">Dados cadastrais</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 text-sm">
          <div><div className="text-xs text-muted-foreground">Código</div><div className="font-mono">{String(detail.code)}</div></div>
          <div><div className="text-xs text-muted-foreground">Forma de pagamento</div><div>{String(detail.payment_type ?? "—").toUpperCase()}</div></div>
          <div><div className="text-xs text-muted-foreground">E-mail</div><div>{String(detail.contact_email ?? "—")}</div></div>
          <div><div className="text-xs text-muted-foreground">Telefone</div><div>{String(detail.contact_phone ?? "—")}</div></div>
          <div><div className="text-xs text-muted-foreground">CPF</div><div>{String(detail.cpf ?? "—")}</div></div>
          <div><div className="text-xs text-muted-foreground">Desconto do cupom</div><div>{detail.discount_pcts ? `${String(detail.discount_pcts)}%` : "—"}</div></div>
          <div><div className="text-xs text-muted-foreground">Comissão</div><div>{detail.commission_pct ? `${String(detail.commission_pct)}%` : "—"}</div></div>
          <div><div className="text-xs text-muted-foreground">Comissão fixa</div><div>{detail.commission_fixed_brl ? `R$ ${String(detail.commission_fixed_brl)}` : "—"}</div></div>
          <div><div className="text-xs text-muted-foreground">Status da conta</div><div>{String(detail.account_status ?? "sem conta")}</div></div>
          <div><div className="text-xs text-muted-foreground">Acesso à conta demo</div><div>{detail.demo_access_enabled ? "permitido" : "revogado"}</div></div>
          {detail.notes ? <div className="col-span-2"><div className="text-xs text-muted-foreground">Notas</div><div>{String(detail.notes)}</div></div> : null}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Cliques", value: String(detail.clicks ?? 0) },
          { label: "Cadastros", value: String(detail.signups ?? 0) },
          { label: "Compradores", value: String(detail.buyers ?? 0) },
          { label: "Faturamento", value: `R$ ${Number(detail.revenue_brl ?? 0).toFixed(0)}` },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="pt-6 text-center">
              <div className="text-2xl font-bold">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Comissão devida</div>
            <div className="text-2xl font-bold text-amber-500">R$ {Number(detail.commission_due_brl ?? 0).toFixed(2)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Comissão já paga</div>
            <div className="text-2xl font-bold text-emerald-600">R$ {Number(detail.commission_paid_brl ?? 0).toFixed(2)}</div>
          </CardContent>
        </Card>
      </div>

      {referredPartners.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Parceiros indicados por este parceiro</CardTitle>
            <p className="text-xs text-muted-foreground">
              Override devido a este parceiro pelas indicações:{" "}
              <span className="text-emerald-600 font-semibold">R$ {Number(detail.referred_override_due_brl || 0).toFixed(2)}</span>
            </p>
          </CardHeader>
          <CardContent>
            {referredPartners.map((p) => (
              <div key={String(p.id)} className="flex items-center justify-between py-2 border-b last:border-0 text-sm">
                <div>
                  <span className="font-semibold">{String(p.name)}</span>
                  <span className="text-muted-foreground"> ({String(p.code)}) · {STATUS_LABEL[String(p.status)] || String(p.status)}</span>
                  <div className="text-xs text-muted-foreground">{Number(p.users_count)} compradores · R$ {Number(p.revenue_brl).toFixed(2)} gerados</div>
                </div>
                <span className="text-emerald-600 text-xs font-semibold">+R$ {Number(p.override_due_brl).toFixed(2)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader><CardTitle className="text-lg">Histórico de pagamentos</CardTitle></CardHeader>
        <CardContent>
          {payments.length === 0 && <p className="text-sm text-muted-foreground">Nenhum pagamento registrado ainda.</p>}
          {payments.map((p) => (
            <div key={String(p.id)} className="flex items-center justify-between py-2 border-b last:border-0 text-sm">
              <div>
                <div className="font-mono">R$ {String(p.amount_brl)}</div>
                <div className="text-xs text-muted-foreground">{p.method ? String(p.method) : "—"} · {p.paid_at ? fmt(String(p.paid_at)) : "—"}</div>
              </div>
              <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">{String(p.status)}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-lg">Acessos à conta demo</CardTitle></CardHeader>
        <CardContent>
          {demoLogs.length === 0 && <p className="text-sm text-muted-foreground">Nenhum acesso registrado ainda.</p>}
          {demoLogs.map((l, i) => (
            <div key={i} className="flex items-center justify-between py-2 border-b last:border-0 text-sm">
              <div className="font-mono text-xs">{String(l.cpf_used)}</div>
              <div className="text-xs text-muted-foreground">{fmt(String(l.created_at))} · {String(l.ip ?? "—")}</div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Modal open={editOpen} onClose={() => setEditOpen(false)} title="Editar parceiro">
        {form && (
          <form onSubmit={submitEdit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Nome"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
              <Field label="Código"><Input className="uppercase" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} required /></Field>
              <Field label="Status">
                <select className="border rounded-md px-2 py-2 text-sm bg-background w-full" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <option value="pending">Pendente</option>
                  <option value="active">Ativo</option>
                  <option value="paused">Pausado</option>
                  <option value="rejected">Rejeitado</option>
                </select>
              </Field>
              <Field label="Forma de pagamento">
                <select className="border rounded-md px-2 py-2 text-sm bg-background w-full" value={form.payment_type} onChange={(e) => setForm({ ...form, payment_type: e.target.value })}>
                  <option value="">—</option>
                  <option value="pf">PF</option>
                  <option value="pj">PJ</option>
                </select>
              </Field>
              <Field label="Comissão (%)"><Input type="number" value={form.commission_pct} onChange={(e) => setForm({ ...form, commission_pct: e.target.value })} /></Field>
              <Field label="Comissão fixa (R$)"><Input type="number" value={form.commission_fixed_brl} onChange={(e) => setForm({ ...form, commission_fixed_brl: e.target.value })} /></Field>
              <Field label="Desconto do cupom (%)">
                <select className="border rounded-md px-2 py-2 text-sm bg-background w-full" value={form.discount_pcts} onChange={(e) => setForm({ ...form, discount_pcts: e.target.value })}>
                  <option value="">—</option>
                  {[5, 10, 15, 20, 25].map((d) => <option key={d} value={d}>{d}%</option>)}
                </select>
              </Field>
              <Field label="CPF"><Input value={form.cpf} onChange={(e) => setForm({ ...form, cpf: e.target.value })} /></Field>
              <Field label="E-mail de contato"><Input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} /></Field>
              <Field label="Telefone de contato"><Input value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} /></Field>
            </div>
            <Field label="Notas"><Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
            {saveErr && <p className="text-sm text-red-600">{saveErr}</p>}
            <Button type="submit" className="w-full" disabled={saving}>{saving ? "Salvando..." : "Salvar alterações"}</Button>
          </form>
        )}
      </Modal>

      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Excluir parceiro">
        <p className="text-sm text-muted-foreground mb-4">
          Tem certeza que deseja excluir <strong>{String(detail.name)}</strong>? Isso remove o parceiro,
          suas atribuições, comissões, pagamentos e logs de acesso à conta demo. Essa ação não pode ser desfeita.
        </p>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setConfirmDelete(false)}>Cancelar</Button>
          <Button type="button" variant="destructive" size="sm" disabled={deleting} onClick={confirmDeletePartner}>
            {deleting ? "Excluindo..." : "Confirmar exclusão"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
