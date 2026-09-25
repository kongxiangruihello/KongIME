#include "qingyan-rime_api.h"
#include <dlfcn.h>
#include <iostream>
#include <stdexcept>
#include <string>
int main(int argc,char**argv){
 if(argc<3)return 2;
 auto lib=dlopen(argv[1],RTLD_NOW|RTLD_GLOBAL);if(!lib){std::cerr<<dlerror();return 2;}
 auto api=((RimeApi*(*)())dlsym(lib,"rime_get_api"))();
 RIME_STRUCT(RimeTraits,t);t.shared_data_dir=argv[2];t.user_data_dir=argv[2];t.app_name="rime.kongime.appearance.test";t.min_log_level=2;t.log_dir="/tmp";
 api->setup(&t);api->deployer_initialize(&t);
 if(!api->deploy_config_file("squirrel.yaml","config_version"))throw std::runtime_error("config compilation failed");
 RimeConfig c;if(!api->config_open("squirrel",&c))throw std::runtime_error("config load failed");
 int size=0;Bool mode=1;char layout[64];char theme[64];
 if(!api->config_get_int(&c,"style/font_point",&size)||size!=24)throw std::runtime_error("font mismatch");
 if(!api->config_get_string(&c,"style/candidate_list_layout",layout,64)||std::string(layout)!="stacked")throw std::runtime_error("layout mismatch");
 if(!api->config_get_string(&c,"style/color_scheme",theme,64)||std::string(theme)!="kongime_dark")throw std::runtime_error("theme mismatch");
 if(!api->config_get_bool(&c,"app_options/com.apple.Terminal/ascii_mode",&mode)||mode)throw std::runtime_error("app mode mismatch");
 if(argc>3 && (!api->config_get_bool(&c,"app_options/com.apple.Terminal/no_inline",&mode)||!mode))throw std::runtime_error("existing app compatibility option lost");
 api->config_close(&c);api->finalize();std::cout<<"PASS: compiled font, layout, theme, app initial mode, preserved compatibility option"<<std::endl;
}
