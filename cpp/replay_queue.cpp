#include "replay_queue.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <stdexcept>
namespace rq {
using Key=std::pair<I,I>;
using Rank=std::tuple<I,I,Key>;
struct Order {int side; double price; I quantity, priority, entered;};
Replay::Replay(std::size_t n):values(16,std::vector<double>(n)),
 snapshots(n*40,std::numeric_limits<double>::quiet_NaN()),valid(n),segment(n),live(n),old_priority(n),new_priority(n){}
Replay replay(const I* rows,std::size_t n,I start,I end,bool reset){
 Replay out(n);
 std::map<Key,Order> orders;
 std::map<double,I> levels[2];
 std::map<std::pair<int,double>,std::map<Rank,I>> queues;
 I unpriced=0,segment=0,previous=-1,barriers=0;
 bool initialized=false;
 double tick=std::numeric_limits<double>::infinity();
 auto adjust=[&](const Order&o,int sign){
  if(o.price<=0){unpriced+=sign;return;}
  auto& level=levels[o.side-1];I quantity=level[o.price]+sign*o.quantity;
  if(quantity<0)throw std::invalid_argument("negative reconstructed depth");
  if(quantity)level[o.price]=quantity;else level.erase(o.price);
 };
 for(std::size_t i=0;i<n;++i){
  const I* r=rows+i*10;
  I time=r[0],date=r[1],id=r[2],side=r[3],price_raw=r[4],scale=r[5],quantity=r[6],priority=r[7];
  char action=static_cast<char>(r[8]);
  if(action=='F'||action=='Y')++barriers;
  if(action=='F'){
   orders.clear();levels[0].clear();levels[1].clear();queues.clear();unpriced=0;previous=-1;initialized=true;
  }else{
   if(!initialized)throw std::invalid_argument("missing source reset");
   if(action!='A'&&action!='Y'&&action!='M'&&action!='D')throw std::invalid_argument("unknown action");
   Key key{date,id};auto found=orders.find(key);bool has=found!=orders.end();Order old{};
   if((action=='M'||action=='D')&&!has)throw std::invalid_argument("update for unknown order");
   if(action=='A'&&has)throw std::invalid_argument("duplicate add");
   if(has){
    old=found->second;adjust(old,-1);
    auto level_key=std::make_pair(old.side,old.price);auto& queue=queues.at(level_key);
    queue.erase(Rank{old.priority,old.entered,key});if(queue.empty())queues.erase(level_key);
    out.values[7][i]=old.side;out.values[8][i]=old.price;out.values[9][i]=old.quantity;out.values[10][i]=old.entered;out.old_priority[i]=old.priority;
   }
   if(action=='D'){orders.erase(key);out.values[15][i]=old.quantity;}
   else{
    if(side==5)side=2;if(side==-1&&has)side=old.side;
    double price=(price_raw==-1&&has)?old.price:static_cast<double>(price_raw)/std::pow(10.0,scale);
    if(quantity==-1&&has)quantity=old.quantity;
    if((side!=1&&side!=2)||quantity<0||!std::isfinite(price))throw std::invalid_argument("invalid order side or volume");
    I reported=priority;priority=reported!=-1?reported:(has?old.priority:time);
    bool changed=!has||(old.side!=side||old.price!=price)||(has&&reported!=-1&&reported!=old.priority)||(has&&action=='M'&&reported==-1&&reset);
    if(changed&&reported==-1)priority=time;
    I entered=changed?static_cast<I>(i):old.entered;
    Order next{static_cast<int>(side),price,quantity,priority,entered};orders[key]=next;adjust(next,1);
    queues[{next.side,price}][Rank{priority,entered,key}]=quantity;
    out.values[11][i]=side;out.values[12][i]=price;out.values[13][i]=quantity;out.values[14][i]=entered;out.new_priority[i]=priority;
    if(has&&action=='M'&&old.side==side&&old.price==price)out.values[15][i]=std::max<I>(0,old.quantity-quantity);
   }
  }
  out.live[i]=orders.size();out.segment[i]=-(static_cast<I>(n)+1)+barriers;
  if(time<start||time>=end)continue;
  if(unpriced||levels[0].size()<10||levels[1].size()<10||levels[0].rbegin()->first>=levels[1].begin()->first){previous=-1;continue;}
  if(previous<0||static_cast<I>(i)!=previous+1)++segment;
  previous=i;out.valid[i]=1;out.segment[i]=segment*(n+1)+barriers;
  double last=0;auto bid=levels[0].rbegin();auto ask=levels[1].begin();
  for(int k=0;k<10;++k,++bid){
   out.snapshots[i*40+k*2]=bid->first;out.snapshots[i*40+k*2+1]=bid->second;
   if(k)tick=std::min(tick,std::abs(bid->first-last));last=bid->first;
  }
  for(int k=0;k<10;++k,++ask){
   out.snapshots[i*40+20+k*2]=ask->first;out.snapshots[i*40+20+k*2+1]=ask->second;
   if(k)tick=std::min(tick,std::abs(ask->first-last));last=ask->first;
  }
  double bp=levels[0].rbegin()->first,ap=levels[1].begin()->first;
  out.values[0][i]=bp;out.values[1][i]=ap;
  out.values[2][i]=levels[0].rbegin()->second;out.values[3][i]=levels[1].begin()->second;
  out.values[4][i]=queues.at({1,bp}).size();out.values[5][i]=queues.at({2,ap}).size();out.values[6][i]=tick;
 }
 for(const auto&[level,queue]:queues)for(const auto&[rank,size]:queue){
  const auto&[priority,entered,key]=rank;
  out.state.emplace_back(level.first,level.second,priority,entered,key.first,key.second,size);
 }
 return out;
}
Paths::Paths(std::size_t n):values(11,std::vector<double>(n,std::numeric_limits<double>::quiet_NaN())),fill(n,-1),adverse(n,-1),first_fill(n),first_adverse(n),simultaneous(n){}
Paths paths(const std::array<const double*,16>&e,const std::uint8_t*valid,const I*segment,std::size_t n,const I*placement,std::size_t count,int side,int horizon,const double*tick,int latency){
 Paths out(count);int direction=side==1?1:-1;
 for(std::size_t k=0;k<count;++k){
  I p=placement[k];double price=e[side==1?0:1][p],ahead=e[side==1?2:3][p],entry_mid=(e[0][p]+e[1][p])/2;
  out.values[0][k]=ahead;out.values[1][k]=e[side==1?4:5][p];out.values[2][k]=price;bool alive=true;
  for(int offset=1;offset<=horizon;++offset){
   I j=std::min<I>(p+offset,n-1);alive=alive&&(p+offset<static_cast<I>(n))&&valid[j]&&segment[j]==segment[p];
   double mid=(e[0][j]+e[1][j])/2;
   if(alive&&out.adverse[k]<0&&direction*(mid-entry_mid)<=-tick[k]+1e-10)out.adverse[k]=offset;
   bool active=alive&&out.fill[k]<0,old_here=e[7][j]==side&&e[8][j]==price,was_ahead=old_here&&e[10][j]<=p;
   if(active&&old_here&&!was_ahead&&ahead<=0&&e[15][j]>=1)out.fill[k]=offset;
   bool still_ahead=e[11][j]==side&&e[12][j]==price&&e[14][j]<=p;
   if(active)ahead+=(still_ahead?e[13][j]:0)-(was_ahead?e[9][j]:0);
   if(active&&ahead< -1e-8)throw std::invalid_argument("negative virtual queue ahead");
  }
  I f=out.fill[k],a=out.adverse[k];
  out.first_fill[k]=f>0&&(a<0||f<a);out.first_adverse[k]=a>0&&(f<0||a<f);out.simultaneous[k]=f>0&&f==a;
  I fi=std::min<I>(p+std::max<I>(f,0),n-1);double fill_mid=(e[0][fi]+e[1][fi])/2;
  int offsets[3]={1,5,10};
  for(int o=0;o<4;++o){
   I future=o==3?p+horizon-latency:fi+offsets[o];
   if(f>0&&future>=fi&&future<static_cast<I>(n)&&valid[future]&&segment[future]==segment[p]){
    double mid=(e[0][future]+e[1][future])/2;
    out.values[3+o*2][k]=direction*(mid-fill_mid)/fill_mid*1e4;
    out.values[4+o*2][k]=2*direction*(mid-price)/price*1e4;
   }
  }
 }
 return out;
}
}
