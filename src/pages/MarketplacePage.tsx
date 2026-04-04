import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLanguage } from '@/contexts/LanguageContext';
import { ArrowLeft, Plus, ShoppingCart, Package, Phone, X, MapPin } from 'lucide-react';
import BottomNav from '@/components/BottomNav';

interface Listing {
  id: string;
  product: string;
  quantity: string;
  price: string;
  unit: string;
  district: string;
  seller: string;
  phone: string;
  category: string;
}

const MarketplacePage: React.FC = () => {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'all' | 'my'>('all');
  const [showAddForm, setShowAddForm] = useState(false);
  const [product, setProduct] = useState('');
  const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState('');
  const [unit, setUnit] = useState('kg');
  const [description, setDescription] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const sampleListings: Listing[] = [
    { id: '1', product: 'Rice (Basmati)', quantity: '500 kg', price: '₹42', unit: 'kg', district: 'Belagavi', seller: 'Ramesh K.', phone: '+91 98765 43210', category: 'Grains' },
    { id: '2', product: 'Tomatoes', quantity: '200 kg', price: '₹25', unit: 'kg', district: 'Dharwad', seller: 'Suresh M.', phone: '+91 87654 32109', category: 'Vegetables' },
    { id: '3', product: 'Sugarcane', quantity: '2 Tons', price: '₹3500', unit: 'quintal', district: 'Bagalkot', seller: 'Anand P.', phone: '+91 76543 21098', category: 'Cash Crops' },
    { id: '4', product: 'Mangoes (Alphonso)', quantity: '100 kg', price: '₹120', unit: 'kg', district: 'Ratnagiri', seller: 'Vijay D.', phone: '+91 65432 10987', category: 'Fruits' },
    { id: '5', product: 'Groundnut', quantity: '300 kg', price: '₹65', unit: 'kg', district: 'Kurnool', seller: 'Lakshmi R.', phone: '+91 54321 09876', category: 'Cash Crops' },
  ];

  const filtered = sampleListings.filter(l =>
    l.product.toLowerCase().includes(searchQuery.toLowerCase()) ||
    l.district.toLowerCase().includes(searchQuery.toLowerCase())
  );

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
          onClick={() => setShowAddForm(true)}
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

      {/* Listings */}
      <div className="px-5 space-y-3">
        {filtered.map((listing) => (
          <div key={listing.id} className="glass-card p-4">
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
              <span className="text-sm font-extrabold text-primary">{listing.price}/{listing.unit}</span>
            </div>
            <div className="flex items-center gap-3 mb-3 text-xs text-muted-foreground">
              <span>📦 {listing.quantity}</span>
              <span className="flex items-center gap-0.5"><MapPin className="w-3 h-3" />{listing.district}</span>
              <span>👤 {listing.seller}</span>
            </div>
            <button className="w-full py-2 rounded-lg bg-primary/10 text-primary text-xs font-bold flex items-center justify-center gap-1.5">
              <Phone className="w-3.5 h-3.5" />
              {t('contactSeller')}
            </button>
          </div>
        ))}
      </div>

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
                <select className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1">
                  <option>Grains</option>
                  <option>Vegetables</option>
                  <option>Fruits</option>
                  <option>Cash Crops</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-bold text-muted-foreground">{t('description')}</label>
                <textarea value={description} onChange={e => setDescription(e.target.value)} rows={3} className="w-full bg-secondary rounded-lg px-3 py-2.5 text-sm text-foreground outline-none mt-1 resize-none" />
              </div>
              <button
                onClick={() => setShowAddForm(false)}
                className="w-full gradient-primary text-primary-foreground py-3 rounded-xl font-bold text-sm"
              >
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
