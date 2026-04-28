import { useState, useEffect } from 'react';
import axios from 'axios';
import { ArrowUpRight, ArrowDownLeft, Clock, CheckCircle2, XCircle, LayoutDashboard, Wallet, History, AlertCircle } from 'lucide-react';
import { cn } from './lib/utils';

const MERCHANTS = [
    { id: "9936752a-c907-4451-b115-adfbb13f519c", name: "Stark Industries (₹100 seed)" },
    { id: "0c730c84-6a53-4cad-9829-931ba03ebdce", name: "Wayne Enterprises (₹0 seed)" },
    { id: "f8de1ba2-4bb5-4947-87e9-cd23be40a7c2", name: "Acme Corp (₹150,000 seed)" }
];
const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

const formatPaise = (paise) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', minimumFractionDigits: 2 }).format(paise / 100);

const formatEntryType = (type) => {
    switch (type) {
        case 'payout_hold': return 'Withdrawal';
        case 'payout_refund': return 'Refunded Withdrawal';
        case 'customer_payment_simulation': return 'Customer Payment';
        default: return type.replace(/_/g, ' ');
    }
};

export default function Dashboard() {
    const [merchantId, setMerchantId] = useState(MERCHANTS[0].id);
    const [data, setData] = useState(null);
    const [amount, setAmount] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const fetchDashboard = async () => {
        try {
            const res = await axios.get(`${API_BASE}/merchants/${merchantId}/dashboard`);
            setData(res.data);
        } catch (err) {
            console.error(err);
        }
    };

    useEffect(() => {
        setData(null); // Show loading skeleton on switch
        fetchDashboard();
        const interval = setInterval(fetchDashboard, 3000); // Aggressive Live sync
        return () => clearInterval(interval);
    }, [merchantId]);

    const handlePayout = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            const idempotencyKey = crypto.randomUUID();
            await axios.post(`${API_BASE}/payouts`, {
                amount_paise: parseInt(amount) * 100, // UI maps to INR visually, strictly Paise on the wire
                bank_account_id: "bank_" + Math.random().toString(36).substring(7)
            }, {
                headers: {
                    'Idempotency-Key': idempotencyKey,
                    'X-Merchant-ID': merchantId
                }
            });
            setAmount('');
            fetchDashboard();
        } catch (err) {
            setError(err.response?.data?.error || "Payout request gracefully blocked");
        } finally {
            setLoading(false);
        }
    };

    if (!data) return (
        <div className="min-h-screen flex items-center justify-center bg-white text-zinc-500 font-sans tracking-tight">
            <div className="flex flex-col items-center gap-3">
                <Clock className="w-5 h-5 animate-spin text-zinc-400" />
                <p className="text-sm">Securely pulling ledger...</p>
            </div>
        </div>
    );

    return (
        <div className="min-h-screen bg-white text-zinc-900 font-sans selection:bg-zinc-100">
            <div className="max-w-4xl mx-auto px-6 py-12 md:py-16">

                {/* Header - Linear Style (Muted text, tight tracking, borderless feel) */}
                <header className="mb-12 flex flex-col md:flex-row md:items-end justify-between border-b border-zinc-100 pb-6 gap-4">
                    <div>
                        <div className="flex items-center gap-2 mb-2">
                            <span className="relative flex h-2 w-2">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                            </span>
                            <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">Live Polling</p>
                        </div>
                        <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
                    </div>
                    <div className="flex flex-col relative items-end">
                        <select
                            value={merchantId}
                            onChange={(e) => setMerchantId(e.target.value)}
                            className="appearance-none bg-zinc-50 border border-zinc-200 text-zinc-900 text-sm font-medium rounded-lg pl-3 pr-8 py-1.5 outline-none focus:ring-1 focus:ring-zinc-400 cursor-pointer"
                        >
                            {MERCHANTS.map(m => (
                                <option key={m.id} value={m.id}>{m.name}</option>
                            ))}
                        </select>
                        {/* Custom Dropdown Arrow */}
                        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-zinc-500">
                            <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" /></svg>
                        </div>
                    </div>
                </header>

                {/* Metrics Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-12">
                    <div className="border border-zinc-200 rounded-xl p-5 bg-white shadow-sm ring-1 ring-zinc-900/5 flex flex-col justify-between">
                        <h2 className="text-sm font-medium text-zinc-500 flex items-center gap-1.5 mb-3">
                            <Wallet className="w-4 h-4" /> Available Balance
                        </h2>
                        <p className="text-3xl font-medium tracking-tight tabular-nums text-zinc-900">
                            {formatPaise(data.balance_paise)}
                        </p>
                    </div>

                    <div className="border border-zinc-200 rounded-xl p-5 bg-zinc-50 border-dashed flex flex-col justify-between">
                        <h2 className="text-sm font-medium text-zinc-400 flex items-center gap-1.5 mb-3">
                            <Clock className="w-4 h-4" /> Held Funds (In Flight)
                        </h2>
                        <p className="text-3xl font-medium tracking-tight tabular-nums text-zinc-400 border-b border-dashed border-zinc-300 pb-1 w-max">
                            {formatPaise(data.held_balance_paise)}
                        </p>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr] gap-12 text-zinc-900">

                    {/* Main Action Area */}
                    <div className="md:col-span-1 space-y-6">
                        <div>
                            <h2 className="text-sm font-semibold text-zinc-900 mb-1">Request Withdrawal</h2>
                            <p className="text-zinc-500 text-xs mb-5">Funds lock immediately for bank processing.</p>

                            <form onSubmit={handlePayout} className="space-y-4">
                                <div>
                                    <div className="relative">
                                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400 font-medium text-sm">₹</span>
                                        <input
                                            type="number"
                                            min="1"
                                            step="1"
                                            value={amount}
                                            onChange={(e) => setAmount(e.target.value)}
                                            className="w-full pl-7 pr-3 py-2 bg-white border border-zinc-200 rounded-lg outline-none focus:border-zinc-400 focus:ring-1 focus:ring-zinc-400 transition-all text-sm font-medium tabular-nums shadow-sm placeholder:text-zinc-300"
                                            placeholder="0.00"
                                            required
                                        />
                                    </div>
                                </div>
                                {error && (
                                    <div className="p-3 bg-red-50/50 border border-red-100 rounded-md flex items-start gap-2 text-red-600 text-xs font-medium content-end animate-in fade-in slide-in-from-top-1">
                                        <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                                        <span>{error}</span>
                                    </div>
                                )}
                                <button
                                    disabled={loading || !amount}
                                    className="w-full bg-zinc-900 text-white rounded-lg px-4 py-2.5 text-sm font-medium hover:bg-zinc-800 disabled:opacity-40 disabled:hover:bg-zinc-900 transition-all shadow-sm flex justify-center items-center h-10"
                                >
                                    {loading ? <Clock className="w-4 h-4 animate-spin opacity-70" /> : 'Withdraw'}
                                </button>
                            </form>
                        </div>
                    </div>

                    {/* History Lists - Implements Linear flat-list UI */}
                    <div className="space-y-12">

                        {/* Payouts Table (Flat list) */}
                        <section>
                            <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <History className="w-3.5 h-3.5" /> Payout Lifecycle
                            </h2>

                            <div className="divide-y divide-zinc-100 -mx-3">
                                {data.payouts.length === 0 ? (
                                    <div className="px-3 py-4 text-xs text-zinc-400">Ledger clear.</div>
                                ) : data.payouts.slice(0, 10).map((p) => (
                                    <div key={p.id} className="px-3 py-3 flex items-center justify-between group hover:bg-zinc-50 rounded-md transition-colors">

                                        {/* Linear Two-Line Structure */}
                                        <div className="flex items-center gap-3">
                                            {p.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-zinc-300 group-hover:text-emerald-500 transition-colors" />}
                                            {p.status === 'failed' && <XCircle className="w-4 h-4 text-zinc-300 group-hover:text-red-500 transition-colors" />}
                                            {(p.status === 'pending' || p.status === 'processing') && <Clock className="w-4 h-4 text-zinc-400/80 group-hover:text-orange-500 transition-colors" />}

                                            <div>
                                                <p className={cn("text-sm font-medium capitalize leading-none mb-1", p.status === 'failed' ? 'text-zinc-500 line-through' : 'text-zinc-900')}>{p.status}</p>
                                                <p className="text-[11px] text-zinc-400 font-mono leading-none tracking-tight">req_{p.id.split('-')[0]}</p>
                                            </div>
                                        </div>

                                        <div className="text-right">
                                            <p className={cn("text-sm font-medium tabular-nums leading-none mb-1", p.status === 'failed' ? "text-zinc-400" : "text-zinc-900")}>
                                                {formatPaise(p.amount_paise)}
                                            </p>
                                            <p className="text-[10px] text-zinc-400 leading-none">{new Date(p.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </section>

                        {/* Atomic Ledger Log */}
                        <section>
                            <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <LayoutDashboard className="w-3.5 h-3.5" /> Immutable Log
                            </h2>
                            <div className="divide-y divide-zinc-100/80 -mx-3">
                                {data.ledger.map((l) => (
                                    <div key={l.id} className="px-3 py-2 flex items-center justify-between hover:bg-zinc-50 rounded-md transition-colors">
                                        <div className="flex items-center gap-3">
                                            <div className={cn("flex flex-col items-center justify-center p-1 rounded shadow-sm ring-1 ring-zinc-900/5", l.amount_paise >= 0 ? "bg-emerald-50 text-emerald-600" : "bg-white text-zinc-600")}>
                                                {l.amount_paise >= 0 ? <ArrowDownLeft className="w-3 h-3" /> : <ArrowUpRight className="w-3 h-3" />}
                                            </div>
                                            <p className="text-xs font-medium text-zinc-600 capitalize tracking-tight">{formatEntryType(l.entry_type)}</p>
                                        </div>
                                        <p className={cn("text-xs font-mono tabular-nums", l.amount_paise < 0 ? "text-zinc-900" : "text-emerald-600")}>
                                            {l.amount_paise > 0 ? '+' : ''}{formatPaise(l.amount_paise)}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </section>

                    </div>
                </div>
            </div>
        </div>
    );
}
