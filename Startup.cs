using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.HttpsPolicy;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.ViewFeatures;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using AdventureWorks.Web.Models;
using Microsoft.EntityFrameworkCore;
using Microsoft.AspNetCore.Authentication.Cookies;

namespace AdventureWorks.Web
{
    public class Startup
    {
        public Startup(IConfiguration configuration)
        {
            Configuration = configuration;
        }

        public IConfiguration Configuration { get; }

        // This method gets called by the runtime. Use this method to add services to the container.
        public void ConfigureServices(IServiceCollection services)
        {
            services.Configure<CookiePolicyOptions>(options =>
            {
                // This lambda determines whether user consent for non-essential cookies is needed for a given request.
                options.CheckConsentNeeded = context => true;
                options.MinimumSameSitePolicy = SameSiteMode.None;
            });


            // BEFORE BASELINE (demo-only): cookie auth for seeded demo customers.
            services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
                .AddCookie(o => { o.LoginPath = "/Account/Login"; o.Cookie.IsEssential = true; });
            services.AddSingleton<AdventureWorks.Web.Demo.FullDb>();
            services.Configure<CookieTempDataProviderOptions>(o => o.Cookie.IsEssential = true);

            // Phase 8 (ADR 0009): Showcase:FrameAncestors = origins allowed to embed this app in the showcase "Before App" tab.
            if (!string.IsNullOrWhiteSpace(Configuration["Showcase:FrameAncestors"]))
                services.AddAntiforgery(o => o.SuppressXFrameOptionsHeader = true);
            services.AddMvc().SetCompatibilityVersion(CompatibilityVersion.Version_2_1);
            services.AddDbContext<sampledbContext>(options =>
        options.UseSqlServer(Configuration.GetConnectionString("sampledbContext")));
        }

        // This method gets called by the runtime. Use this method to configure the HTTP request pipeline.
        public void Configure(IApplicationBuilder app, IHostingEnvironment env)
        {
            //if (env.IsDevelopment())
            //{
            //    /*app.UseDeveloperExceptionPage();*/
            //}
            //else
            //{
            //    app.UseExceptionHandler("/Home/Error");
            //    app.UseHsts();
            //}

            app.UseDeveloperExceptionPage();


            // BEFORE BASELINE: HTTPS redirect is skipped when no HTTPS endpoint is configured (containers/CI).
            if (Configuration["DisableHttpsRedirection"] != "true") app.UseHttpsRedirection();
            var frameAncestors = Configuration["Showcase:FrameAncestors"]?.Trim();
            if (!string.IsNullOrEmpty(frameAncestors))
                app.Use((ctx, next) => { ctx.Response.Headers["Content-Security-Policy"] = "frame-ancestors 'self' " + frameAncestors; return next(); });
            app.UseStaticFiles();
            app.UseCookiePolicy();
            app.UseAuthentication();

            app.UseMvc(routes =>
            {
                routes.MapRoute(
                    name: "default",
                    template: "{controller=ProductCategories}/{action=Index}/{id?}");
            });
        }
    }
}
