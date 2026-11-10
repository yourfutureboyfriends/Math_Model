// A fundamental-data provider for real LEAN fed by the platform's free data, so `Fundamental` objects in universe
// selectors carry values instead of LEAN's empty defaults: has_fundamental_data, market cap, shares, EPS, ratios and
// statement lines from SEC EDGAR filings (point in time: from the session after filing), and today's Morningstar sector
// code (sector history is not free). Coarse fields (price, volume, dollar volume) still come from LEAN's own coarse
// provider. Values live in equity/usa/fundamental/free/YYYYMMDD.csv (header: sid,<FundamentalProperty names>), one file
// per session, written by api/quant/leanrun.py; values for session D (known by D's close) are read with D's coarse
// data, which LEAN hands to selectors on the next session.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using QuantConnect.Data.Fundamental;
using QuantConnect.Data.UniverseSelection;
using QuantConnect.Interfaces;

namespace QuantConnect.FreeData
{
    public class FreeFundamentalDataProvider : CoarseFundamentalDataProvider
    {
        private string _dir;
        private DateTime[] _dates = Array.Empty<DateTime>();
        private DateTime _loaded = DateTime.MinValue;
        private Dictionary<string, Dictionary<FundamentalProperty, double>> _rows = new();

        public override void Initialize(IDataProvider dataProvider, bool liveMode)
        {
            base.Initialize(dataProvider, liveMode);
            _dir = Path.Combine(Globals.DataFolder, "equity", "usa", "fundamental", "free");
            if (Directory.Exists(_dir))
            {
                _dates = Directory.GetFiles(_dir, "*.csv")
                    .Select(f => DateTime.ParseExact(Path.GetFileNameWithoutExtension(f), "yyyyMMdd", CultureInfo.InvariantCulture))
                    .OrderBy(d => d).ToArray();
            }
        }

        public override T Get<T>(DateTime time, SecurityIdentifier securityIdentifier, FundamentalProperty name)
        {
            lock (this)
            {
                Load(time);
                _rows.TryGetValue(securityIdentifier.ToString(), out var row);
                if (name == FundamentalProperty.HasFundamentalData)
                {
                    return (T)(object)(row != null);
                }
                if (row != null && row.TryGetValue(name, out var v) && !double.IsNaN(v))
                {
                    var t = Nullable.GetUnderlyingType(typeof(T)) ?? typeof(T);
                    if (t == typeof(double)) return (T)(object)v;
                    if (t == typeof(decimal)) return (T)(object)(decimal)v;
                    if (t == typeof(long)) return (T)(object)(long)Math.Round(v);
                    if (t == typeof(int)) return (T)(object)(int)Math.Round(v);
                    if (t == typeof(bool)) return (T)(object)(v != 0);
                    if (t == typeof(string)) return (T)(object)v.ToString(CultureInfo.InvariantCulture);
                }
            }
            return base.Get<T>(time, securityIdentifier, name);
        }

        private void Load(DateTime time)
        {
            // `time` is the data's own session (LEAN stamps Fundamental with the coarse file's date; the selection runs on
            // the next session): the file for that session, or the newest before it
            var cutoff = time.Date;
            var i = Array.BinarySearch(_dates, cutoff);
            if (i < 0) i = ~i - 1;
            var date = i >= 0 ? _dates[i] : DateTime.MinValue;
            if (date == _loaded) return;
            _loaded = date;
            _rows = new();
            if (date == DateTime.MinValue) return;
            var lines = File.ReadAllLines(Path.Combine(_dir, $"{date:yyyyMMdd}.csv"));
            if (lines.Length == 0) return;
            var head = lines[0].Split(',');
            var props = head.Skip(1).Select(h => Enum.TryParse<FundamentalProperty>(h, out var p) ? (FundamentalProperty?)p : null).ToArray();
            foreach (var line in lines.Skip(1))
            {
                var c = line.Split(',');
                var row = new Dictionary<FundamentalProperty, double>();
                for (var k = 1; k < c.Length && k <= props.Length; k++)
                {
                    if (props[k - 1] is FundamentalProperty p && c[k].Length > 0 &&
                        double.TryParse(c[k], NumberStyles.Float, CultureInfo.InvariantCulture, out var v))
                    {
                        row[p] = v;
                    }
                }
                _rows[c[0]] = row;
            }
        }
    }
}
