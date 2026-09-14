#include "replay_queue.hpp"
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <cstring>
namespace py=pybind11;
using A=py::array_t<double,py::array::c_style|py::array::forcecast>;
using IA=py::array_t<rq::I,py::array::c_style|py::array::forcecast>;
using BA=py::array_t<std::uint8_t,py::array::c_style|py::array::forcecast>;
const char* names[]={"bid","ask","bid_size","ask_size","bid_orders","ask_orders","tick","old_side","old_price","old_quantity","old_entered","new_side","new_price","new_quantity","new_entered","execution"};
template<class T>py::array_t<T> array(const std::vector<T>&v){py::array_t<T>a(v.size());if(!v.empty())std::memcpy(a.mutable_data(),v.data(),v.size()*sizeof(T));return a;}
py::array_t<bool> boolean(const std::vector<std::uint8_t>&v){py::array_t<bool>a(v.size());for(std::size_t i=0;i<v.size();++i)a.mutable_data()[i]=v[i]!=0;return a;}
PYBIND11_MODULE(_replay_queue,m){
 m.def("replay",[](IA rows,rq::I start,rq::I end,bool reset){
  if(rows.ndim()!=2||rows.shape(1)!=10)throw std::invalid_argument("expected n by 10 input");
  auto n=rows.shape(0);auto result=[&]{py::gil_scoped_release release;return rq::replay(rows.data(),n,start,end,reset);}();
  py::dict out;for(int i=0;i<16;++i)out[names[i]]=array(result.values[i]);
  out["valid"]=boolean(result.valid);out["segment"]=array(result.segment);out["live_orders"]=array(result.live);
  out["old_priority"]=array(result.old_priority);out["new_priority"]=array(result.new_priority);
  auto snapshots=array(result.snapshots);snapshots.resize({n,static_cast<py::ssize_t>(40)});out["snapshots"]=snapshots;
  out["final_queues"]=py::cast(result.state);return out;
 });
 m.def("paths",[](py::dict events,IA placement,int side,int horizon,A tick,int latency){
  BA valid(events["valid"]);IA segment(events["segment"]);
  if(valid.ndim()!=1||segment.ndim()!=1||placement.ndim()!=1||tick.ndim()!=1||tick.size()!=placement.size()||segment.size()!=valid.size())throw std::invalid_argument("invalid diagnostic array dimensions");
  auto n=valid.size();std::array<A,16> storage;std::array<const double*,16>ptrs;
  for(int i=0;i<16;++i){storage[i]=A(events[names[i]]);if(storage[i].ndim()!=1||storage[i].size()!=n)throw std::invalid_argument("mismatched event arrays");ptrs[i]=storage[i].data();}
  if((side!=1&&side!=2)||(horizon!=10&&horizon!=20&&horizon!=50)||(latency!=0&&latency!=1&&latency!=5))throw std::invalid_argument("unsupported frozen policy");
  for(py::ssize_t k=0;k<placement.size();++k)if(placement.data()[k]<0||placement.data()[k]>=n||!valid.data()[placement.data()[k]]||!(tick.data()[k]>0))throw std::invalid_argument("invalid placement or tick");
  auto result=[&]{py::gil_scoped_release release;return rq::paths(ptrs,valid.data(),segment.data(),n,placement.data(),placement.size(),side,horizon,tick.data(),latency);}();
  py::dict out;out["queue_ahead"]=array(result.values[0]);out["orders_ahead"]=array(result.values[1]);out["placement_price"]=array(result.values[2]);
  out["fill_time"]=array(result.fill);out["adverse_time"]=array(result.adverse);
  out["fill_before_adverse"]=boolean(result.first_fill);out["adverse_before_fill"]=boolean(result.first_adverse);out["simultaneous"]=boolean(result.simultaneous);
  const char* offsets[]={"1","5","10","remaining"};
  for(int i=0;i<4;++i){out[py::str(std::string("markout_")+offsets[i])]=array(result.values[3+i*2]);out[py::str(std::string("spread_")+offsets[i])]=array(result.values[4+i*2]);}
  return out;
 });
}
