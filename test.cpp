#include <bits/stdc++.h>
using namespace std;

struct BigInt {
    vector<int> d;
    
    BigInt() {}
    
    BigInt(long long v) {
        while (v > 0) {
            d.push_back(v % 10);
            v /= 10;
        }
        if (d.empty()) d.push_back(0);
    }
    
    void trim() {
        while (d.size() > 1 && d.back() == 0) d.pop_back();
    }
    
    BigInt operator+(const BigInt& o) const {
        BigInt res;
        int carry = 0;
        size_t n = max(d.size(), o.d.size());
        res.d.resize(n);
        for (size_t i = 0; i < n; i++) {
            int sum = carry;
            if (i < d.size()) sum += d[i];
            if (i < o.d.size()) sum += o.d[i];
            res.d[i] = sum % 10;
            carry = sum / 10;
        }
        if (carry > 0) res.d.push_back(carry);
        return res;
    }
    
    BigInt& operator+=(const BigInt& o) {
        *this = *this + o;
        return *this;
    }
    
    BigInt operator*(int v) const {
        BigInt res;
        long long carry = 0;
        res.d.resize(d.size());
        for (size_t i = 0; i < d.size(); i++) {
            long long prod = (long long)d[i] * v + carry;
            res.d[i] = prod % 10;
            carry = prod / 10;
        }
        while (carry > 0) {
            res.d.push_back(carry % 10);
            carry /= 10;
        }
        return res;
    }
    
    bool operator<(const BigInt& o) const {
        if (d.size() != o.d.size()) return d.size() < o.d.size();
        for (int i = d.size() - 1; i >= 0; i--) {
            if (d[i] != o.d[i]) return d[i] < o.d[i];
        }
        return false;
    }
    
    bool operator>(const BigInt& o) const { return o < *this; }
    bool operator<=(const BigInt& o) const { return !(o < *this); }
    bool operator>=(const BigInt& o) const { return !(*this < o); }
    
    string toString() const {
        string s;
        for (int i = d.size() - 1; i >= 0; i--) s += char('0' + d[i]);
        return s;
    }
};

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    
    int n, m;
    if (!(cin >> n >> m)) return 0;
    
    if (n <= 0 || m <= 0) {
        cout << "0\n";
        return 0;
    }
    
    vector<BigInt> pow2(m + 1);
    pow2[0] = BigInt(1);
    for (int i = 1; i <= m; i++) {
        pow2[i] = pow2[i-1] * 2;
    }
    
    vector<vector<BigInt>> dp(m, vector<BigInt>(m));
    BigInt total;
    
    for (int row = 0; row < n; row++) {
        vector<int> a(m);
        for (int j = 0; j < m; j++) {
            cin >> a[j];
        }
        
        for (int i = 0; i < m; i++) {
            dp[i][i] = BigInt(a[i]) * pow2[m];
        }
        
        for (int len = 2; len <= m; len++) {
            int expIdx = m - len + 1;
            for (int i = 0; i + len - 1 < m; i++) {
                int j = i + len - 1;
                BigInt left = dp[i+1][j] + BigInt(a[i]) * pow2[expIdx];
                BigInt right = dp[i][j-1] + BigInt(a[j]) * pow2[expIdx];
                dp[i][j] = left > right ? left : right;
            }
        }
        
        total += dp[0][m-1];
    }
    
    cout << total.toString() << "\n";
    
    return 0;
}