import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { useAuth } from '@/contexts/AuthContext';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { ArrowLeft, Plus, ShoppingCart, Package, Phone, X, MapPin, Loader2 } from 'lucide-react';
import BottomNav from '@/components/BottomNav';

interface Listing {
  id: string;
  product: string;
  quantity: string;
  price: number;
  unit: string;
  district: string | null;
  seller: string;
  phone: string;
  category: string;
  description: string | null;
  created_by: string | null;
  created_at: string;
}

const CATEGORIES = ['Grains', 'Vegetables', 'Fruits', 'Cash Crops', 'Other'];

const MarketplacePage: React.FC = () => {
  const { t } = useLanguage();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'all' | 'my'>('all');
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [setupNeeded, setSetupNeeded] = useState(false);
  const [posting, setPosting] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [product, setProduct] = useState('');
  const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState('');
  const [unit, setUnit] = useState('kg');
  const [category, setCategory] = useState(CATEGORIES[0]);
  const [description, setDescription] = useState('');
  const [seller, setSeller] = useState(() => localStorage.getItem('profile_name') || '');
  const [phone, setPhone] = useState('');
  const [district, setDistrict] = useState(() => localStorage.getItem('profile_district') || '');
  const [searchQuery, setSearchQuery] = useState('');

  const loadListings = async () => {
    setLoading(true);
    setSetupNeeded(false);
    const { data, error } = await supabase
      .from('marketplace_listings')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(200);
    if (error) {
      // Postgres "table does not exist" surfaces as PGRST205 via PostgREST
      if (error.code === 'PGRST205' || /marketplace_listings/.test(error.message)) {
        setSetupNeeded(true);
      } else {
        console.error('Marketplace load error:', error);
        toast.error('Could not load listings');
      }
      setListings([]);
    } else {
      setListings((data as Listing[]) ?? []);
    }
    setLoading(false);
  };

  useEffect(() => {
    loadListings();
  }, []);

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase();
    const byTab = activeTab === 'my' && user
      ? listings.filter(l => l.created_by === user.id)
      : listings;
    if (!q) return byTab;
    return byTab.filter(l =>
      l.product.toLowerCase().includes(q) ||
      (l.district ?? '').toLowerCase().includes(q)
    );
  }, [listings, searchQuery, activeTab, user]);

  const canPost = product.trim() && quantity.trim() && Number(price) > 0 &&
    seller.trim() && phone.trim().length >= 10;

  const postListing = async () => {
    if (!user) {
      toast.error('Please sign in from the home page to post a listing');
      return;
    }
    if (!canPost) return;
    setPosting(true);
    const { error } = await supabase
      .from('marketplace_listings')
      .insert({
        product: product.trim(),
        quantity: quantity.trim(),
        price: Number(price),
        unit,
        category,
        description: description.trim() || null,
        district: district.trim() || null,
        seller: seller.trim(),
        phone: phone.trim(),
        created_by: user.id,
      });
    setPosting(false);
    if (error) {
      if (error.code === 'PGRST205' || /marketplace_listings/.test(error.message)) {
        setSetupNeeded(true);
      }
      console.error('Marketplace insert error:', error);
      toast.error(`Could not post listing: ${error.message}`);
      return;
    }
    toast.success('Listing posted');
    setShowAddForm(false);
    setProduct(''); setQuantity(''); setPrice('');
    setDescription(''); setPhone('');
    loadListings();
  };

  return (
    <div className="min-h-screen bg-background pb-20">
      {/* Header */}
      <div className="px-5 pt-5 pb-3 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
          <ArrowLeft className="w-4 h-4 text-foreground" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-extrabold text-foreground">{t('marketplace')}</h1>
          <p className="text-xs text-muted-foreground">{t('sellYourProduce')}</p>
        </div>
        <button
          onClick={() => {
            setSeller(s => s || localStorage.getItem('profile_name') || '');
            setDistrict(d => d || localStorage.getItem('profile_district') || '');
            setShowAddForm(true);
          }}
          className="w-9 h-9 rounded-full gradient-primary flex items-center justify-center"
        >
          <Plus className="w-5 h-5 text-primary-foreground" />
        </button>
      </div>

      {/* Search */}
      <div className="px-5 mb-3">
        <input
          type="text"
          placeholder={t('search')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-secondary rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none"
        />
      </div>

      {/* Tabs */}
      <div className="px-5 mb-4">
        <div className="flex gap-2">
          {(['all', 'my'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-all ${
                activeTab === tab ? 'gradient-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'
              }`}
            >
              {tab === 'all' ? t('allListings') : t('myListings')}
            </button>
          ))}
        </div>
      </div>

      {/* Real data states */}
      {setupNeeded && (
        <div className="px-5 mb-4">
          <div className="glass-card p-4 text-sm text-muted-foreground">
            <p className="font-bold text-foreground mb-1">Marketplace is not set up yet</p>
            <p>
              The <code className="text-primary">marketplace_listings</code> table is missing from
              your Supabase project. Run{' '}
              <code className="text-primary">supabase/migrations/20260101000000_marketplace_listings.sql</code>{' '}
              in your Supabase SQL editor, then reopen this page.
            </p>
          </div>
        </div>
      )}
      {loading && (
        <div className="px-5 py-10 flex justify-center">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
        </div>
      )}
      {!loading && !setupNeeded && filtered.length === 0 && activeTab === 'my' && !user && (
        <div className="px-5">
          <div className="glass-card p-4 text-sm text-muted-foreground">Sign in to see your listings.</div>
        </div>
      )}
      {!loading && !setupNeeded && filtered.length === 0 && (user || activeTab === 'all') && (
        <div className="px-5">
          <div className="glass-card p-4 text-sm text-muted-foreground">
            {activeTab === 'all'
              ? 'No listings yet. Use the + button above to post the first one.'
              : 'No listings of yours yet. Use the + button above to post one.'}
          </div>
        </div>
      )}

      {/* Listings */}
      {!loading && filtered.map((listing) => (
        <div key={listing.id} className="px-5 mb-3">
          <div className="glass-card p-4">
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Package className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground">{listing.product}</h3>
                  <p className="text-[10px] text-muted-foreground">{listing.category}</p>
                </div>
              </div>
              <span className="text-sm font-extrabold text-primary">₹{listing.price}/{listing.unit}</span>
            </div>
            <div className="flex items-center gap-3 mb-3 text-xs text-muted-foreground">
              <span>📦 {listing.quantity}</span>
              <span className="flex items-center gap-0.5"><MapPin className="w-3 h-3" />{listing.district || '—'}</span>
              <span>👤 {listing.seller}</span>
            </div>
            {listing.description && (
              <p className="text-xs text-muted-foreground mb-3">{listing.description}</p>
            )}
            <a
              href={`tel:${listing.phone}`}
              className="block w-full py-2 rounded-lg bg-primary/10 text-primary text-xs font-bold flex items-center justify-center gap-1.5"
            >
              <Phone className="w-3.5 h-3.5" />
              {t('contactSeller')}
            </a>
          </div>
        </div>
      ))}

      {/* Add Listing Modal */}
      {showAddForm && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-end">
          <div className="w-full max-w-lg mx-auto bg-card rounded-t-2xl p-5 border border-border/50 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-extrabold text-foreground">{t('addListing')}</h2>
              <button onClick={() => setShowAddForm(false)} className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center">
                <X className="w-4 h-4" />
              </button>
            </div>
            {!user && (
              <div className="mb-3 p-3 rounded-lg bg-amber-500/10 text-amber-600 text-xs">
                You are not signed in. Sign in from the home page first — your account
                links the listing to you for the “My Listings” tab.
              </div>
            )}
            <div className="space-y-3">
              <div>
                <label className="text-xs font-bold text-muted-foreground">{t('productName')}</label>
                <input value={product} onChange={e => setProduct(e.target.value)} className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-bold text-muted-foreground">{t('quantity')}</label>
                  <input value={quantity} onChange={e => setQuantity(e.target.value)} className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1" placeholder="e.g. 500 kg" />
                </div>
                <div>
                  <label className="text-xs font-bold text-muted-foreground">{t('pricePerUnit')}</label>
                  <div className="flex gap-1 mt-1">
                    <input value={price} onChange={e => setPrice(e.target.value)} className="flex-1 bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none" placeholder="₹" />
                    <select value={unit} onChange={e => setUnit(e.target.value)} className="bg-secondary rounded-lg px-2 py-2.5 text-xs text-foreground outline-none">
                      <option value="kg">{t('perKg')}</option>
                      <option value="quintal">{t('perQuintal')}</option>
                    </select>
                  </div>
                </div>
              </div>
              <div>
                <label className="text-xs font-bold text-muted-foreground">{t('category')}</label>
                <select value={category} onChange={e => setCategory(e.target.value)} className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1">
                  {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-bold text-muted-foreground">Seller name</label>
                  <input value={seller} onChange={e => setSeller(e.target.value)} className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1" />
                </div>
                <div>
                  <label className="text-xs font-bold text-muted-foreground">{t('phoneNumber')}</label>
                  <input value={phone} onChange={e => setPhone(e.target.value)} className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1" placeholder="10-digit" />
                </div>
              </div>
              <div>
                <label className="text-xs font-bold text-muted-foreground">District</label>
                <input value={district} onChange={e => setDistrict(e.target.value)} className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1" placeholder="From your profile" />
              </div>
              <div>
                <label className="text-xs font-bold text-muted-foreground">{t('description')}</label>
                <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3} className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1 resize-none" />
              </div>
              <button
                onClick={postListing}
                disabled={!user || !canPost || posting}
                className="w-full gradient-primary text-primary-foreground py-3 rounded-xl font-bold text-sm disabled:opacity-40 flex items-center justify-center gap-2"
              >
                {posting && <Loader2 className="w-4 h-4 animate-spin" />}
                {t('postListing')}
              </button>
            </div>
          </div>
        </div>
      )}

      <BottomNav />
    </div>
  );
};

export default MarketplacePage;
