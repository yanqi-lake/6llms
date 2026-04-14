#include <bits/stdc++.h>
using namespace std;
using int64 = long long;
using i128 = __int128_t;

int64 mod_pow(int64 a, int64 e, int64 mod) {
    int64 res = 1 % mod;
    a %= mod;
    while (e > 0) {
        if (e & 1) res = (i128)res * a % mod;
        a = (i128)a * a % mod;
        e >>= 1;
    }
    return res;
}

int64 exgcd(int64 a, int64 b, int64 &x, int64 &y) {
    if (b == 0) {
        x = 1;
        y = 0;
        return a;
    }
    int64 x1, y1;
    int64 g = exgcd(b, a % b, x1, y1);
    x = y1;
    y = x1 - y1 * (a / b);
    return g;
}

int64 mod_inv(int64 a, int64 mod) {
    int64 x, y;
    int64 g = exgcd(a, mod, x, y);
    if (g != 1) return -1;
    x %= mod;
    if (x < 0) x += mod;
    return x;
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    
    int64 N, K, M, P;
    if (!(cin >> N >> K >> M >> P)) return 0;
    
    int64 pow = mod_pow(M, K - 1, P);
    int64 inv2 = mod_inv(2, P);
    
    int64 N_mod = N % P;
    int64 term1 = (i128)pow * N_mod % P;
    
    int64 k_minus_1 = (K - 1) % P;
    int64 m_plus_1 = (M + 1) % P;
    int64 half = (i128)k_minus_1 * m_plus_1 % P;
    half = (i128)half * inv2 % P;
    
    int64 term2 = (i128)pow * half % P;
    
    int64 ans = (term1 - term2) % P;
    if (ans < 0) ans += P;
    
    cout << ans << "\n";
    return 0;
}